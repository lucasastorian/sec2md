from __future__ import annotations

import re
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Union, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser
from sec2md.utils import median, clean_text
from sec2md.table_parser import TableParser
from sec2md.models import Page, Element
from sec2md.element_builder import build_elements_for_pages, augment_html_with_ids

BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "br", "hr", "ul", "ol", "li"}
BOLD_TAGS = {"b", "strong"}
ITALIC_TAGS = {"i", "em"}

_css_decl = re.compile(r"^[a-zA-Z\-]+\s*:\s*[^;]+;\s*$")
ITEM_HEADER_CELL_RE = re.compile(r"^\s*Item\s+([0-9IVX]+)\.\s*$", re.I)
PART_HEADER_CELL_RE = re.compile(r"^\s*Part\s+([IVX]+)\s*$", re.I)

logger = logging.getLogger(__name__)


@dataclass
class TextBlockInfo:
    """Tracks XBRL TextBlock context during parsing."""
    name: str
    title: Optional[str] = None


class Parser:
    """Document parser with support for regular tables and pseudo-tables."""

    def __init__(self, content: str):
        self.soup = BeautifulSoup(content, "lxml")
        self.includes_table = False
        self.pages: Dict[int, List[str]] = defaultdict(list)
        self.page_segments: Dict[int, List[Tuple[str, Optional[Tag], Optional[TextBlockInfo]]]] = defaultdict(list)
        self.input_char_count = len(self.soup.get_text())
        self.current_text_block: Optional[TextBlockInfo] = None
        self.continuation_map: Dict[str, TextBlockInfo] = {}
        self.footer_page_numbers: Dict[int, int] = {}

    @staticmethod
    def _is_text_block_tag(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        if el.name not in ('ix:nonnumeric', 'nonnumeric'):
            return False
        name = el.get('name', '')
        if 'TextBlock' not in name:
            return False
        return name.startswith('us-gaap:') or name.startswith('cyd:')

    @staticmethod
    def _find_text_block_tag_in_children(el: Tag) -> Optional[Tag]:
        """Search up to 2 levels deep for a TextBlock tag."""
        if not isinstance(el, Tag):
            return None
        if Parser._is_text_block_tag(el):
            return el
        for child in el.children:
            if isinstance(child, Tag):
                if Parser._is_text_block_tag(child):
                    return child
                for grandchild in child.children:
                    if isinstance(grandchild, Tag) and Parser._is_text_block_tag(grandchild):
                        return grandchild
        return None

    @staticmethod
    def _extract_text_block_info(el: Tag) -> Optional[TextBlockInfo]:
        if not isinstance(el, Tag):
            return None
        name = el.get('name', '')
        if not name or 'TextBlock' not in name:
            return None

        tag_text = el.get_text(strip=True) or ''

        if tag_text and len(tag_text) < 200:
            title = tag_text
        else:
            name_part = name.split(':')[-1].replace('TextBlock', '')
            title = re.sub(r'([A-Z])', r' \1', name_part).strip()
            title = re.sub(r'\s+', ' ', title)

        return TextBlockInfo(name=name, title=title)

    @staticmethod
    def _is_continuation_tag(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        return el.name in ('ix:continuation', 'continuation')

    @staticmethod
    def _is_bold(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower()
        return (
                "font-weight:700" in style
                or "font-weight:bold" in style
                or el.name in BOLD_TAGS
        )

    @staticmethod
    def _is_italic(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower()
        return (
                "font-style:italic" in style
                or el.name in ITALIC_TAGS
        )

    @staticmethod
    def _is_block(el: Tag) -> bool:
        return isinstance(el, Tag) and el.name in BLOCK_TAGS

    @staticmethod
    def _is_absolutely_positioned(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return "position:absolute" in style

    @staticmethod
    def _extract_top_px(el: Tag, fallback_height: float = 10000.0) -> Optional[float]:
        """Extract Y position from top: or bottom: CSS."""
        if not isinstance(el, Tag):
            return None
        style = el.get("style", "")
        m_top = re.search(r'top:\s*(\d+(?:\.\d+)?)px', style)
        if m_top:
            return float(m_top.group(1))
        m_bot = re.search(r'bottom:\s*(\d+(?:\.\d+)?)px', style)
        if m_bot:
            return fallback_height - float(m_bot.group(1))
        return None

    @staticmethod
    def _is_inline_display(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return "display:inline-block" in style or "display:inline;" in style

    @staticmethod
    def _has_break_before(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return (
                "page-break-before:always" in style
                or "break-before:page" in style
                or "break-before:always" in style
        )

    @staticmethod
    def _has_break_after(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return (
                "page-break-after:always" in style
                or "break-after:page" in style
                or "break-after:always" in style
        )

    @staticmethod
    def _is_hidden(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return "display:none" in style

    @staticmethod
    def _wrap_markdown(el: Tag) -> str:
        bold = Parser._is_bold(el)
        italic = Parser._is_italic(el)
        if bold and italic:
            return "***"
        if bold:
            return "**"
        if italic:
            return "*"
        return ""

    @staticmethod
    def _is_plausible_page_number(num: int, min_val: int = 1) -> bool:
        return min_val <= num <= 9999 and not (1900 <= num <= 2100)

    def _try_merge_inline_spans(self, last_text: str, current_text: str, last_source: Optional[Tag],
                                 current_source: Optional[Tag]) -> Optional[str]:
        if not (last_source and current_source and
                isinstance(last_source, Tag) and isinstance(current_source, Tag)):
            return None

        if last_source.parent != current_source.parent:
            return None

        last_stripped = last_text.rstrip()
        current_stripped = current_text.lstrip()

        # Merge **text** **text** -> **text text**
        if last_stripped.endswith('**') and current_stripped.startswith('**'):
            last_ws = last_text[len(last_stripped):]
            current_ws = current_text[:len(current_text) - len(current_stripped)]
            return last_stripped[:-2] + last_ws + current_ws + current_stripped[2:]

        # Merge *text* *text* -> *text text* (but not bold)
        if (last_stripped.endswith('*') and current_stripped.startswith('*') and
            not last_stripped.endswith('**')):
            last_ws = last_text[len(last_stripped):]
            current_ws = current_text[:len(current_text) - len(current_stripped)]
            return last_stripped[:-1] + last_ws + current_ws + current_stripped[1:]

        return None

    def _append(self, page_num: int, s: str, source_node: Optional[Tag] = None, text_block: Optional[TextBlockInfo] = None) -> None:
        if not s:
            return

        tb = text_block if text_block is not None else self.current_text_block

        buf = self.pages[page_num]
        seg_buf = self.page_segments[page_num]

        if buf and seg_buf:
            last_text = buf[-1]
            last_seg = seg_buf[-1]
            last_source = last_seg[1]

            merged = self._try_merge_inline_spans(last_text, s, last_source, source_node)
            if merged:
                buf[-1] = merged
                seg_buf[-1] = (merged, last_source, last_seg[2])
                return

        self.pages[page_num].append(s)
        self.page_segments[page_num].append((s, source_node, tb))

    def _blankline_before(self, page_num: int) -> None:
        buf = self.pages[page_num]
        seg_buf = self.page_segments[page_num]
        if not buf:
            return
        if not buf[-1].endswith("\n"):
            buf.append("\n")
            seg_buf.append(("\n", None, self.current_text_block))
        if len(buf) >= 2 and buf[-1] == "\n" and buf[-2] == "\n":
            return
        buf.append("\n")
        seg_buf.append(("\n", None, self.current_text_block))

    def _blankline_after(self, page_num: int) -> None:
        self._blankline_before(page_num)

    def _process_text_node(self, node: NavigableString) -> str:
        text = clean_text(str(node))
        if text and _css_decl.match(text):
            return ""
        return text

    def _process_element(self, element: Union[Tag, NavigableString]) -> str:
        if isinstance(element, NavigableString):
            return self._process_text_node(element)

        if element.name == "table":
            eff_rows = self._effective_rows(element)
            if len(eff_rows) <= 1:
                cells = eff_rows[0] if eff_rows else []
                return self._one_row_table_to_text(cells)

            self.includes_table = True
            return TableParser(element).md().strip()

        if element.name in {"ul", "ol"}:
            items = []
            for li in element.find_all("li", recursive=False):
                item_text = self._process_element(li).strip()
                if item_text:
                    item_text = item_text.lstrip("•·∙◦▪▫-").strip()
                    items.append(item_text)
            if not items:
                return ""
            if element.name == "ol":
                return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
            return "\n".join(f"- {t}" for t in items)

        if element.name == "li":
            parts = [self._process_element(c) for c in element.children]
            return " ".join(p for p in parts if p).strip()

        parts: List[str] = []
        for child in element.children:
            if isinstance(child, NavigableString):
                t = self._process_text_node(child)
                if t:
                    parts.append(t)
            else:
                t = self._process_element(child)
                if t:
                    parts.append(t)

        text = " ".join(p for p in parts if p).strip()
        if not text:
            return ""

        wrap = self._wrap_markdown(element)
        return f"{wrap}{text}{wrap}" if wrap else text

    def _extract_page_number_from_footer(self, footer_el: Tag) -> Optional[int]:
        text = footer_el.get_text(" ", strip=True)
        if not text:
            return None

        m = re.search(r'\|\s*(\d{1,4})\s*$', text)
        if m:
            num = int(m.group(1))
            if self._is_plausible_page_number(num):
                return num

        m = re.search(r'\bPage\s+(\d{1,4})\b', text, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            if self._is_plausible_page_number(num):
                return num

        m = re.search(r'\b(\d{1,4})\s*$', text)
        if m:
            num = int(m.group(1))
            if self._is_plausible_page_number(num, min_val=10):
                return num

        return None

    def _is_footer_element(self, el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False

        style = (el.get("style") or "").lower().replace(" ", "")

        if not ("position:absolute" in style and "bottom:0" in style):
            return False

        if "width:100%" in style:
            return True

        text = el.get_text(" ", strip=True)
        if text and len(text) < 200:
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in ["form 10-k", "form 10-q", "form 8-k", "page"]):
                return True

        return False

    def _extract_absolutely_positioned_children(self, container: Tag) -> List[Tag]:
        positioned_children = []
        for child in container.children:
            if isinstance(child, Tag) and self._is_absolutely_positioned(child):
                if child.get_text(strip=True) or AbsolutelyPositionedTableParser._is_spacer(child):
                    positioned_children.append(child)
        return positioned_children

    def _compute_line_gaps(self, elements: List[Tag]) -> List[float]:
        y_positions = []
        for el in elements:
            y = self._extract_top_px(el)
            if y is not None:
                y_positions.append(y)

        if len(y_positions) < 2:
            return []

        y_positions.sort()
        gaps = [y_positions[i + 1] - y_positions[i] for i in range(len(y_positions) - 1)]
        return [g for g in gaps if 5 < g < 100]

    def _split_positioned_groups(self, elements: List[Tag], gap_threshold: Optional[float] = None) -> List[List[Tag]]:
        """Split positioned elements into groups using adaptive gap threshold."""
        if not elements:
            return []

        if gap_threshold is None:
            line_gaps = self._compute_line_gaps(elements)
            if line_gaps:
                median_gap = median(line_gaps)
                gap_threshold = min(1.2 * median_gap, 30.0)
                logger.debug(f"Adaptive gap threshold: {gap_threshold:.1f}px (median line gap: {median_gap:.1f}px)")
            else:
                gap_threshold = 30.0

        element_positions = []
        for el in elements:
            y = self._extract_top_px(el)
            if y is not None:
                element_positions.append((y, el))

        if not element_positions:
            return [elements]

        element_positions.sort(key=lambda x: x[0])

        groups = []
        current_group = [element_positions[0][1]]
        last_y = element_positions[0][0]

        for y, el in element_positions[1:]:
            if y - last_y > gap_threshold:
                if current_group:
                    groups.append(current_group)
                current_group = [el]
            else:
                current_group.append(el)
            last_y = y

        if current_group:
            groups.append(current_group)

        final_groups = []
        for group in groups:
            final_groups.extend(self._split_by_column_transition(group))

        logger.debug(f"Split {len(elements)} elements into {len(final_groups)} groups (threshold: {gap_threshold:.1f}px)")
        return final_groups

    def _split_by_column_transition(self, elements: List[Tag]) -> List[List[Tag]]:
        """Split a group if it transitions from multi-column to single-column."""
        if len(elements) < 6:
            return [elements]

        element_data = []
        for el in elements:
            style = el.get("style", "")
            left_match = re.search(r'left:\s*(\d+(?:\.\d+)?)px', style)
            y = self._extract_top_px(el)
            if left_match and y is not None:
                element_data.append((float(left_match.group(1)), y, el))

        if not element_data:
            return [elements]

        element_data.sort(key=lambda x: x[1])

        rows = []
        current_row = [element_data[0]]
        last_y = element_data[0][1]

        for left, top, el in element_data[1:]:
            if abs(top - last_y) <= 15:
                current_row.append((left, top, el))
            else:
                rows.append(current_row)
                current_row = [(left, top, el)]
                last_y = top

        if current_row:
            rows.append(current_row)

        def count_columns(row):
            return len(set(left for left, _, _ in row))

        split_point = None
        for i in range(len(rows) - 3):
            current_cols = count_columns(rows[i])
            next_cols = count_columns(rows[i + 1])

            if current_cols >= 2 and next_cols == 1:
                following_single = sum(1 for j in range(i + 1, min(i + 4, len(rows)))
                                       if count_columns(rows[j]) == 1)
                if following_single >= 2:
                    split_point = i + 1
                    logger.debug(f"Column transition at row {i + 1} ({current_cols} cols -> {next_cols} col)")
                    break

        if split_point is None:
            return [elements]

        split_y = rows[split_point][0][1]

        group1 = [el for left, top, el in element_data if top < split_y]
        group2 = [el for left, top, el in element_data if top >= split_y]

        result = []
        if group1:
            result.append(group1)
        if group2:
            result.append(group2)

        return result if result else [elements]

    def _process_absolutely_positioned_container(self, container: Tag, page_num: int) -> int:
        positioned_children = self._extract_absolutely_positioned_children(container)

        if not positioned_children:
            current = page_num
            for child in container.children:
                current = self._stream_pages(child, current)
            return current

        content_elements = []

        for child in positioned_children:
            if self._is_footer_element(child):
                display_page = self._extract_page_number_from_footer(child)
                if display_page is not None:
                    self.footer_page_numbers[page_num] = display_page
                    logger.debug(f"Extracted display_page={display_page} from footer on page {page_num}")
            else:
                content_elements.append(child)

        if not content_elements:
            return page_num

        groups = self._split_positioned_groups(content_elements)

        for i, group in enumerate(groups):
            table_parser = AbsolutelyPositionedTableParser(group)

            if table_parser.is_table_like():
                self.includes_table = True
                markdown_table = table_parser.to_markdown()
                if markdown_table:
                    self._append(page_num, markdown_table, source_node=group[0] if group else None)
                    self._blankline_after(page_num)
            else:
                text = table_parser.to_text()
                if text:
                    if i > 0:
                        self._blankline_before(page_num)
                    self._append(page_num, text, source_node=group[0] if group else None)

        return page_num

    def _restore_text_block(self, started: bool, has_continuation: bool,
                            ends_block: bool, previous: Optional[TextBlockInfo]) -> None:
        if started and not has_continuation:
            self.current_text_block = None if ends_block else previous

    def _stream_pages(self, root: Union[Tag, NavigableString], page_num: int = 1) -> int:
        """Walk the DOM once; split only on CSS break styles."""
        if isinstance(root, Tag) and self._has_break_before(root):
            page_num += 1

        if isinstance(root, NavigableString):
            t = self._process_text_node(root)
            if t:
                parent = root.parent if isinstance(root.parent, Tag) else None
                self._append(page_num, t + " ", source_node=parent)
            return page_num

        if not isinstance(root, Tag):
            return page_num

        if self._is_hidden(root):
            return page_num

        text_block_started = False
        text_block_has_continuation = False
        continuation_ends_text_block = False
        previous_text_block = self.current_text_block

        if self._is_continuation_tag(root):
            cont_id = root.get('id')
            if cont_id and cont_id in self.continuation_map:
                self.current_text_block = self.continuation_map[cont_id]
                text_block_started = True
                continuedat = root.get('continuedat')
                if continuedat:
                    text_block_has_continuation = True
                    self.continuation_map[continuedat] = self.current_text_block
                else:
                    continuation_ends_text_block = True

        is_absolutely_positioned = self._is_absolutely_positioned(root)
        has_positioned_children = not is_absolutely_positioned and any(
            isinstance(child, Tag) and self._is_absolutely_positioned(child)
            for child in root.children
        )

        if has_positioned_children and root.name == "div":
            current = self._process_absolutely_positioned_container(root, page_num)
            if self._has_break_after(root):
                current += 1
            self._restore_text_block(text_block_started, text_block_has_continuation,
                                     continuation_ends_text_block, previous_text_block)
            return current

        is_inline_display = self._is_inline_display(root)
        is_block = (self._is_block(root) and root.name not in {"br", "hr"}
                    and not is_inline_display and not is_absolutely_positioned)

        # Check block elements for new TextBlocks (allows new notes to replace old ones across pages)
        if is_block:
            tb_tag = self._find_text_block_tag_in_children(root)
            if tb_tag:
                tb_info = self._extract_text_block_info(tb_tag)
                if tb_info:
                    is_new = (self.current_text_block is None or
                              self.current_text_block.name != tb_info.name)
                    if is_new:
                        self.current_text_block = tb_info
                        text_block_started = True
                        continuedat = tb_tag.get('continuedat')
                        if continuedat:
                            text_block_has_continuation = True
                            self.continuation_map[continuedat] = tb_info

        if is_block:
            self._blankline_before(page_num)

        if root.name in {"table", "ul", "ol"}:
            t = self._process_element(root)
            if t:
                self._append(page_num, t, source_node=root)
            self._blankline_after(page_num)
            if self._has_break_after(root):
                page_num += 1
            self._restore_text_block(text_block_started, text_block_has_continuation,
                                     continuation_ends_text_block, previous_text_block)
            return page_num

        wrap = self._wrap_markdown(root)
        if wrap and not is_block:
            t = self._process_element(root)
            if t:
                self._append(page_num, t + " ", source_node=root)
            if self._has_break_after(root):
                page_num += 1
            self._restore_text_block(text_block_started, text_block_has_continuation,
                                     continuation_ends_text_block, previous_text_block)
            return page_num

        current = page_num
        for child in root.children:
            current = self._stream_pages(child, current)

        if is_block:
            self._blankline_after(current)

        if self._has_break_after(root):
            current += 1

        self._restore_text_block(text_block_started, text_block_has_continuation,
                                 continuation_ends_text_block, previous_text_block)
        return current

    def _detect_display_page_numbers(self, pages: List[Page]) -> List[Page]:
        if not pages:
            return pages

        if self.footer_page_numbers:
            logger.debug(f"Using {len(self.footer_page_numbers)} footer-extracted page numbers")
            for page in pages:
                if page.number in self.footer_page_numbers:
                    page.display_page = self.footer_page_numbers[page.number]
            return pages

        candidates: List[Tuple[int, Optional[int]]] = []

        for page in pages:
            candidate = self._extract_page_number_from_content(page.content)
            candidates.append((page.number, candidate))

        if self._validate_page_number_sequence(candidates):
            for page in pages:
                idx = page.number - 1
                if idx < len(candidates):
                    page.display_page = candidates[idx][1]

        return pages

    def _extract_page_number_from_content(self, content: str) -> Optional[int]:
        if not content:
            return None

        lines = content.split('\n')

        check_lines = []
        if len(lines) >= 3:
            check_lines.extend(lines[:3])
            check_lines.extend(lines[-3:])
        else:
            check_lines = lines

        for line in check_lines:
            line = line.strip()

            if len(line) > 100:
                continue

            if re.match(r'^\d{1,4}$', line):
                num = int(line)
                if self._is_plausible_page_number(num, min_val=10):
                    return num

            patterns = [
                r'\bPage\s+(\d{1,4})\b',
                r'\b(\d{1,4})\s*\|',
                r'\|\s*(\d{1,4})\b',
            ]

            for pattern in patterns:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    num = int(m.group(1))
                    if self._is_plausible_page_number(num):
                        return num

        return None

    def _validate_page_number_sequence(self, candidates: List[Tuple[int, Optional[int]]]) -> bool:
        valid_pairs = [(pnum, dpage) for pnum, dpage in candidates if dpage is not None]

        if len(valid_pairs) < 5:
            return False

        prev_display = None
        increasing_count = 0
        total_transitions = 0

        for _, display_page in valid_pairs:
            if prev_display is not None:
                total_transitions += 1
                if display_page == prev_display + 1:
                    increasing_count += 2
                elif display_page > prev_display:
                    increasing_count += 1
            prev_display = display_page

        if total_transitions == 0:
            return False

        return increasing_count / total_transitions >= 0.8

    @staticmethod
    def _strip_page_breadcrumbs(content: str) -> str:
        """Remove repeated bare PART/ITEM breadcrumbs from page tops."""
        if not content:
            return content

        lines = content.split("\n")
        idx = 0

        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return content

        part_line = lines[idx].strip()
        if not re.match(r"^(?:\*\*|__)?\s*PART\s+[IVXLC]+\s*(?:\*\*|__)?$", part_line, re.IGNORECASE):
            return content

        idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return content

        item_line = lines[idx].strip()
        # e.g., "ITEM 2" or "ITEM 2, 3, 4" or "ITEM 9, 9A"
        if not re.match(r'^(?:\*\*|__)?\s*ITEM\s+\d{1,2}[A-Z]?(?:\s*,\s*\d{1,2}[A-Z]?)*\s*(?:\*\*|__)?$',
                        item_line,
                        re.IGNORECASE):
            return content

        idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        return "\n".join(lines[idx:])

    def get_pages(self, include_elements: bool = True) -> List[Page]:
        self.pages = defaultdict(list)
        self.page_segments = defaultdict(list)
        self.includes_table = False
        root = self.soup.body if self.soup.body else self.soup
        self._stream_pages(root, page_num=1)

        result: List[Page] = []
        for page_num in sorted(self.pages.keys()):
            raw = "".join(self.pages[page_num])
            raw = re.sub(r"\n{3,}", "\n\n", raw)

            lines: List[str] = []
            for line in raw.split("\n"):
                line = line.strip()
                if line or (lines and lines[-1]):
                    lines.append(line)
            content = "\n".join(lines).strip()
            content = self._strip_page_breadcrumbs(content).strip()

            result.append(Page(number=page_num, content=content, elements=None))

        total_output_chars = sum(len(p.content) for p in result)
        if self.input_char_count > 0:
            retention = total_output_chars / self.input_char_count
            if retention >= 0.95:
                logger.debug(f"Content retention: {100 * retention:.1f}%")

        result = self._detect_display_page_numbers(result)

        if include_elements:
            result = self._add_elements_to_pages(result)

        return result

    def _effective_rows(self, table: Tag) -> list[list[Tag]]:
        rows = []
        for tr in table.find_all('tr', recursive=True):
            cells = tr.find_all(['td', 'th'], recursive=False) or tr.find_all(['td', 'th'], recursive=True)
            texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            if any(texts):
                rows.append(cells)
        return rows

    def _one_row_table_to_text(self, cells: list[Tag]) -> str:
        texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
        if not texts:
            return ""

        first = texts[0]
        if (m := ITEM_HEADER_CELL_RE.match(first)):
            num = m.group(1).upper()
            title = next((t for t in texts[1:] if t), "")
            return f"ITEM {num}. {title}".strip()

        if (m := PART_HEADER_CELL_RE.match(first)):
            roman = m.group(1).upper()
            return f"PART {roman}"

        return " ".join(t for t in texts if t).strip()

    def _add_elements_to_pages(self, pages: List[Page]) -> List[Page]:
        result, block_nodes_map = build_elements_for_pages(pages, self.page_segments)
        page_elements = {}
        for page in result:
            if page.elements:
                page_elements[page.number] = page.elements
        augment_html_with_ids(page_elements, block_nodes_map)
        return result

    def markdown(self) -> str:
        pages = self.get_pages()
        return "\n\n".join(page.content for page in pages if page.content)

    def html(self) -> str:
        return str(self.soup)
