from __future__ import annotations

import re
import logging
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Union, Optional, Tuple
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser, median
from sec2md.table_parser import TableParser
from sec2md.models import Page, Element

BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "br", "hr", "ul", "ol", "li"}
BOLD_TAGS = {"b", "strong"}
ITALIC_TAGS = {"i", "em"}

_ws = re.compile(r"\s+")
_css_decl = re.compile(r"^[a-zA-Z\-]+\s*:\s*[^;]+;\s*$")
ITEM_HEADER_CELL_RE = re.compile(r"^\s*Item\s+([0-9IVX]+)\.\s*$", re.I)
PART_HEADER_CELL_RE = re.compile(r"^\s*Part\s+([IVX]+)\s*$", re.I)

logger = logging.getLogger(__name__)


@dataclass
class TextBlockInfo:
    """Tracks XBRL TextBlock context during parsing."""
    name: str  # e.g., "us-gaap:DebtDisclosureTextBlock"
    title: Optional[str] = None  # e.g., "Note 9 – Debt"


class Parser:
    """Document parser with support for regular tables and pseudo-tables."""

    def __init__(self, content: str):
        self.soup = BeautifulSoup(content, "lxml")
        self.includes_table = False
        self.pages: Dict[int, List[str]] = defaultdict(list)
        # Track DOM provenance and TextBlock: (content, source_node, text_block_info)
        self.page_segments: Dict[int, List[Tuple[str, Optional[Tag], Optional[TextBlockInfo]]]] = defaultdict(list)
        self.input_char_count = len(self.soup.get_text())

        # Track current TextBlock context
        self.current_text_block: Optional[TextBlockInfo] = None
        # Map continuation IDs to TextBlock context
        self.continuation_map: Dict[str, TextBlockInfo] = {}

    @staticmethod
    def _is_text_block_tag(el: Tag) -> bool:
        """Check if element is an ix:nonnumeric with a note-level TextBlock name.

        Only tracks financial notes, not document metadata.
        Tracks: us-gaap:*, cyd:* (notes and disclosures)
        Ignores: dei:* (document metadata)
        """
        if not isinstance(el, Tag):
            return False
        if el.name not in ('ix:nonnumeric', 'nonnumeric'):
            return False
        name = el.get('name', '')
        if 'TextBlock' not in name:
            return False

        # Only track note-level TextBlocks (us-gaap, cyd)
        # Ignore document metadata (dei)
        return name.startswith('us-gaap:') or name.startswith('cyd:')

    @staticmethod
    def _find_text_block_tag_in_children(el: Tag) -> Optional[Tag]:
        """Find TextBlock tag in children (search 2 levels deep).

        Searches children and grandchildren to handle:
        <div>
          <span><ix:nonnumeric>Title</ix:nonnumeric></span>
          <div>Content</div>
        </div>
        """
        if not isinstance(el, Tag):
            return None

        # Check if current element is the TextBlock tag
        if Parser._is_text_block_tag(el):
            return el

        # Check direct children
        for child in el.children:
            if isinstance(child, Tag):
                if Parser._is_text_block_tag(child):
                    return child
                # Check grandchildren (one more level)
                for grandchild in child.children:
                    if isinstance(grandchild, Tag) and Parser._is_text_block_tag(grandchild):
                        return grandchild

        return None

    @staticmethod
    def _extract_text_block_info(el: Tag) -> Optional[TextBlockInfo]:
        """Extract TextBlock name and title from ix:nonnumeric tag.

        Since we only track outermost TextBlocks, these should have short titles
        (e.g., "Segment Information and Geographic Data") inside the tag.
        """
        if not isinstance(el, Tag):
            return None
        name = el.get('name', '')
        if not name or 'TextBlock' not in name:
            return None

        # Get text content from tag
        tag_text = el.get_text(strip=True) or ''

        # Use tag content if reasonable length (<200 chars is a note title)
        # Otherwise derive from XBRL name
        if tag_text and len(tag_text) < 200:
            title = tag_text
        else:
            # Fallback: Derive from XBRL name
            # "SegmentReportingDisclosureTextBlock" -> "Segment Reporting Disclosure"
            import re
            name_part = name.split(':')[-1].replace('TextBlock', '')
            # Insert spaces before capitals
            title = re.sub(r'([A-Z])', r' \1', name_part).strip()
            # Clean up double spaces
            title = re.sub(r'\s+', ' ', title)

        return TextBlockInfo(name=name, title=title)

    @staticmethod
    def _is_continuation_tag(el: Tag) -> bool:
        """Check if element is an ix:continuation tag."""
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
        """Check if element has position:absolute"""
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return "position:absolute" in style

    @staticmethod
    def _is_inline_display(el: Tag) -> bool:
        """Check if element has display:inline or display:inline-block"""
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
        """Check if element has display:none"""
        if not isinstance(el, Tag):
            return False
        style = (el.get("style") or "").lower().replace(" ", "")
        return "display:none" in style

    @staticmethod
    def _clean_text(text: str) -> str:
        # Remove zero-width spaces, BOM, normalize NBSP
        text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
        return _ws.sub(" ", text).strip()

    @staticmethod
    def _wrap_markdown(el: Tag) -> str:
        """Return the prefix/suffix markdown wrapper for this element."""
        bold = Parser._is_bold(el)
        italic = Parser._is_italic(el)
        if bold and italic:
            return "***"
        if bold:
            return "**"
        if italic:
            return "*"
        return ""

    def _append(self, page_num: int, s: str, source_node: Optional[Tag] = None, text_block: Optional[TextBlockInfo] = None) -> None:
        if s:
            self.pages[page_num].append(s)
            # Use current_text_block if not explicitly provided
            tb = text_block if text_block is not None else self.current_text_block
            self.page_segments[page_num].append((s, source_node, tb))

    def _blankline_before(self, page_num: int) -> None:
        """Ensure exactly one blank line before the next block."""
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
        """Mirror `_blankline_before` for symmetry; same rule."""
        self._blankline_before(page_num)

    def _process_text_node(self, node: NavigableString) -> str:
        text = self._clean_text(str(node))
        if text and _css_decl.match(text):
            return ""
        return text

    def _process_element(self, element: Union[Tag, NavigableString]) -> str:
        if isinstance(element, NavigableString):
            return self._process_text_node(element)

        if element.name == "table":
            # Use effective (non-empty) rows for the decision
            eff_rows = self._effective_rows(element)
            if len(eff_rows) <= 1:
                # Flatten single-row "header tables" like Item/Part banners
                cells = eff_rows[0] if eff_rows else []
                text = self._one_row_table_to_text(cells)
                return text

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
            else:
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

    def _extract_absolutely_positioned_children(self, container: Tag) -> List[Tag]:
        """
        Extract all absolutely positioned children from a container.

        Returns:
            List of absolutely positioned child elements
        """
        positioned_children = []
        for child in container.children:
            if isinstance(child, Tag) and self._is_absolutely_positioned(child):
                # Skip elements that are just styling (no text content)
                if child.get_text(strip=True):
                    positioned_children.append(child)
        return positioned_children

    def _compute_line_gaps(self, elements: List[Tag]) -> List[float]:
        """
        Compute gaps between consecutive Y positions (line gaps).

        Returns:
            List of gap sizes in pixels
        """
        y_positions = []
        for el in elements:
            style = el.get("style", "")
            top_match = re.search(r'top:\s*(\d+(?:\.\d+)?)px', style)
            if top_match:
                y_positions.append(float(top_match.group(1)))

        if len(y_positions) < 2:
            return []

        y_positions.sort()
        gaps = [y_positions[i + 1] - y_positions[i] for i in range(len(y_positions) - 1)]
        # Filter out very small gaps (same line) and very large gaps (section breaks)
        gaps = [g for g in gaps if 5 < g < 100]
        return gaps

    def _split_positioned_groups(self, elements: List[Tag], gap_threshold: Optional[float] = None) -> List[List[Tag]]:
        """
        Split positioned elements into separate groups.
        Uses ADAPTIVE gap threshold based on document characteristics.

        Args:
            elements: List of absolutely positioned elements
            gap_threshold: Optional threshold in pixels (if None, computed adaptively)

        Returns:
            List of element groups
        """
        if not elements:
            return []

        # ADAPTIVE THRESHOLD: Learn from the document
        if gap_threshold is None:
            line_gaps = self._compute_line_gaps(elements)
            if line_gaps:
                median_gap = median(line_gaps)
                # Use 1.2x median line gap, capped at 30px
                gap_threshold = min(1.2 * median_gap, 30.0)
                logger.debug(f"Adaptive gap threshold: {gap_threshold:.1f}px (median line gap: {median_gap:.1f}px)")
            else:
                gap_threshold = 30.0  # Fallback

        # Extract Y coordinates
        element_positions = []
        for el in elements:
            style = el.get("style", "")
            top_match = re.search(r'top:\s*(\d+(?:\.\d+)?)px', style)
            if top_match:
                top = float(top_match.group(1))
                element_positions.append((top, el))

        if not element_positions:
            return [elements]

        # Sort by Y position
        element_positions.sort(key=lambda x: x[0])

        # Group by gaps
        groups = []
        current_group = [element_positions[0][1]]
        last_y = element_positions[0][0]

        for y, el in element_positions[1:]:
            gap = y - last_y
            if gap > gap_threshold:
                # Large gap - start new group
                if current_group:
                    groups.append(current_group)
                current_group = [el]
            else:
                current_group.append(el)
            last_y = y

        if current_group:
            groups.append(current_group)

        # Post-process: split groups that transition from multi-column to single-column
        final_groups = []
        for group in groups:
            split_groups = self._split_by_column_transition(group)
            final_groups.extend(split_groups)

        logger.debug(
            f"Split {len(elements)} elements into {len(final_groups)} groups (threshold: {gap_threshold:.1f}px)")
        return final_groups

    def _split_by_column_transition(self, elements: List[Tag]) -> List[List[Tag]]:
        """
        Split a group if it transitions from multi-column (table) to single-column (prose).

        This handles cases where a table is followed immediately by paragraph text
        without a large Y-gap between them.

        Args:
            elements: List of elements in a group

        Returns:
            List of split groups (or original group if no transition found)
        """
        if len(elements) < 6:
            return [elements]

        # Extract X, Y positions for all elements
        element_data = []
        for el in elements:
            style = el.get("style", "")
            left_match = re.search(r'left:\s*(\d+(?:\.\d+)?)px', style)
            top_match = re.search(r'top:\s*(\d+(?:\.\d+)?)px', style)
            if left_match and top_match:
                left = float(left_match.group(1))
                top = float(top_match.group(1))
                element_data.append((left, top, el))

        if not element_data:
            return [elements]

        # Sort by Y position
        element_data.sort(key=lambda x: x[1])

        # Group into rows by Y position (15px tolerance)
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

        # Count unique X positions per row
        def count_columns(row):
            x_positions = set(left for left, _, _ in row)
            return len(x_positions)

        # Find transition point from multi-column to single-column
        split_point = None
        for i in range(len(rows) - 3):  # Need at least 3 rows after split
            current_cols = count_columns(rows[i])
            next_cols = count_columns(rows[i + 1])

            # Transition from 2+ columns to 1 column
            if current_cols >= 2 and next_cols == 1:
                # Check if next 2-3 rows are also single-column (confirms prose pattern)
                following_single = sum(1 for j in range(i + 1, min(i + 4, len(rows)))
                                       if count_columns(rows[j]) == 1)
                if following_single >= 2:
                    split_point = i + 1
                    logger.debug(f"Column transition detected at row {i + 1} ({current_cols} cols -> {next_cols} col)")
                    break

        if split_point is None:
            return [elements]

        # Split at the transition point
        split_y = rows[split_point][0][1]  # Y coordinate of first element in transition row

        group1 = [el for left, top, el in element_data if top < split_y]
        group2 = [el for left, top, el in element_data if top >= split_y]

        result = []
        if group1:
            result.append(group1)
        if group2:
            result.append(group2)

        return result if result else [elements]

    def _process_absolutely_positioned_container(self, container: Tag, page_num: int) -> int:
        """
        Handle containers with absolutely positioned children.

        Step 1: Extract absolutely positioned elements
        Step 2: Split into separate groups by Y-coordinate gaps AND column transitions
        Step 3: Process each group independently (table or text)

        Args:
            container: The container element
            page_num: Current page number

        Returns:
            Updated page number
        """
        # Extract positioned children
        positioned_children = self._extract_absolutely_positioned_children(container)

        if not positioned_children:
            # No positioned children, process normally
            current = page_num
            for child in container.children:
                current = self._stream_pages(child, current)
            return current

        # Split into separate groups (adaptive threshold + column transition detection)
        groups = self._split_positioned_groups(positioned_children)

        # Process each group independently
        for i, group in enumerate(groups):
            table_parser = AbsolutelyPositionedTableParser(group)

            if table_parser.is_table_like():
                # It's a table! Render as markdown table
                self.includes_table = True
                markdown_table = table_parser.to_markdown()
                if markdown_table:
                    # Use first element of group as source node
                    self._append(page_num, markdown_table, source_node=group[0] if group else None)
                    self._blankline_after(page_num)
            else:
                # Not a table - group by visual lines and render as text
                text = table_parser.to_text()
                if text:
                    if i > 0:
                        self._blankline_before(page_num)
                    # Use first element of group as source node
                    self._append(page_num, text, source_node=group[0] if group else None)

        return page_num

    def _stream_pages(self, root: Union[Tag, NavigableString], page_num: int = 1) -> int:
        """Walk the DOM once; split only on CSS break styles."""
        if isinstance(root, Tag) and self._has_break_before(root):
            page_num += 1

        if isinstance(root, NavigableString):
            t = self._process_text_node(root)
            if t:
                # For text nodes, use parent as source
                parent = root.parent if isinstance(root.parent, Tag) else None
                self._append(page_num, t + " ", source_node=parent)
            return page_num

        if not isinstance(root, Tag):
            return page_num

        if self._is_hidden(root):
            return page_num

        # Track XBRL TextBlock context (will be set later after determining if block)
        text_block_started = False
        text_block_has_continuation = False
        previous_text_block = self.current_text_block

        # Check if this is a continuation tag
        continuation_ends_text_block = False
        if self._is_continuation_tag(root):
            cont_id = root.get('id')
            if cont_id and cont_id in self.continuation_map:
                self.current_text_block = self.continuation_map[cont_id]
                text_block_started = True
                # Check if continues further
                continuedat = root.get('continuedat')
                if continuedat:
                    text_block_has_continuation = True
                    self.continuation_map[continuedat] = self.current_text_block
                else:
                    # No continuedat: this continuation tag ENDS the TextBlock
                    # We need to clear the context after processing this tag
                    continuation_ends_text_block = True

        # Check if this is a container with absolutely positioned children
        is_absolutely_positioned = self._is_absolutely_positioned(root)
        has_positioned_children = not is_absolutely_positioned and any(
            isinstance(child, Tag) and self._is_absolutely_positioned(child)
            for child in root.children
        )

        if has_positioned_children and root.name == "div":
            # Special handling for absolutely positioned layouts
            current = self._process_absolutely_positioned_container(root, page_num)
            if self._has_break_after(root):
                current += 1

            # Restore TextBlock context before early return
            if text_block_started and not text_block_has_continuation:
                if continuation_ends_text_block:
                    self.current_text_block = None
                else:
                    self.current_text_block = previous_text_block

            return current

        # Inline-display elements should not trigger blocks
        is_inline_display = self._is_inline_display(root)
        is_block = self._is_block(root) and root.name not in {"br",
                                                              "hr"} and not is_inline_display and not is_absolutely_positioned

        # Check if this block element contains a TextBlock tag in its children
        # ALWAYS check block elements for new TextBlocks (not just when current_text_block is None)
        # This allows new notes to replace old ones across pages
        if is_block:
            tb_tag = self._find_text_block_tag_in_children(root)
            if tb_tag:
                tb_info = self._extract_text_block_info(tb_tag)
                if tb_info:
                    # Only set if it's a DIFFERENT TextBlock (ignore nested duplicates)
                    is_new_text_block = (
                        self.current_text_block is None or
                        self.current_text_block.name != tb_info.name
                    )
                    if is_new_text_block:
                        self.current_text_block = tb_info
                        text_block_started = True
                        # Check for continuedat attribute ON THE TAG ITSELF
                        continuedat = tb_tag.get('continuedat')
                        if continuedat:
                            text_block_has_continuation = True
                            self.continuation_map[continuedat] = tb_info

        if is_block:
            self._blankline_before(page_num)

        # Handle tables and lists atomically
        if root.name in {"table", "ul", "ol"}:
            t = self._process_element(root)
            if t:
                self._append(page_num, t, source_node=root)
            self._blankline_after(page_num)
            if self._has_break_after(root):
                page_num += 1

            # Restore TextBlock context before early return
            if text_block_started and not text_block_has_continuation:
                if continuation_ends_text_block:
                    self.current_text_block = None
                else:
                    self.current_text_block = previous_text_block

            return page_num

        # For inline wrappers (bold/italic), render atomically
        wrap = self._wrap_markdown(root)
        if wrap and not is_block:
            t = self._process_element(root)
            if t:
                self._append(page_num, t + " ", source_node=root)
            if self._has_break_after(root):
                page_num += 1

            # Restore TextBlock context before early return
            if text_block_started and not text_block_has_continuation:
                if continuation_ends_text_block:
                    self.current_text_block = None
                else:
                    self.current_text_block = previous_text_block

            return page_num

        # Stream children for block elements
        current = page_num
        for child in root.children:
            current = self._stream_pages(child, current)

        if is_block:
            self._blankline_after(current)

        if self._has_break_after(root):
            current += 1

        # Restore previous TextBlock context if we started a new one
        # This applies to:
        # 1. Block elements with new TextBlock tags (restore to previous)
        # 2. Continuation tags that END a TextBlock (clear to None)
        # (unless the TextBlock tag has continuedat, meaning it continues elsewhere)
        if text_block_started and not text_block_has_continuation:
            if continuation_ends_text_block:
                # Continuation tag with no continuedat ENDS the TextBlock
                self.current_text_block = None
            else:
                # New TextBlock tag restores to previous context
                self.current_text_block = previous_text_block

        return current

    def get_pages(self, include_elements: bool = True) -> List[Page]:
        """Get parsed pages as Page objects.

        Args:
            include_elements: If True, include structured Element objects with each page

        Returns:
            List of Page objects, optionally with elements
        """
        # Parse content using existing stream parser
        self.pages = defaultdict(list)
        self.page_segments = defaultdict(list)
        self.includes_table = False
        root = self.soup.body if self.soup.body else self.soup
        self._stream_pages(root, page_num=1)

        result: List[Page] = []
        for page_num in sorted(self.pages.keys()):
            raw = "".join(self.pages[page_num])

            # Collapse excessive newlines
            raw = re.sub(r"\n{3,}", "\n\n", raw)

            lines: List[str] = []
            for line in raw.split("\n"):
                line = line.strip()
                if line or (lines and lines[-1]):
                    lines.append(line)
            content = "\n".join(lines).strip()

            result.append(Page(number=page_num, content=content, elements=None))

        # CONTENT-LOSS WATCHDOG
        total_output_chars = sum(len(p.content) for p in result)
        if self.input_char_count > 0:
            retention_ratio = total_output_chars / self.input_char_count
            if retention_ratio < 0.95:
                # logger.warning(f"⚠️  Content loss detected: {100 * (1 - retention_ratio):.1f}% of input lost!")
                # logger.warning(f"   Input: {self.input_char_count} chars, Output: {total_output_chars} chars")
                pass
            else:
                logger.debug(f"✓ Content retention: {100 * retention_ratio:.1f}%")

        # If elements requested, process further
        if include_elements:
            result = self._add_elements_to_pages(result)

        return result

    def _effective_rows(self, table: Tag) -> list[list[Tag]]:
        """Return rows that have at least one non-empty td/th."""
        rows = []
        for tr in table.find_all('tr', recursive=True):
            cells = tr.find_all(['td', 'th'], recursive=False) or tr.find_all(['td', 'th'], recursive=True)
            texts = [self._clean_text(c.get_text(" ", strip=True)) for c in cells]
            if any(texts):
                rows.append(cells)
        return rows

    def _one_row_table_to_text(self, cells: list[Tag]) -> str:
        """Flatten a 1-row table to plain text; upgrade to header when possible."""
        texts = [self._clean_text(c.get_text(" ", strip=True)) for c in cells]
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

        # generic flatten (avoid markdown pipes which might be misread later)
        return " ".join(t for t in texts if t).strip()

    def _add_elements_to_pages(self, pages: List[Page]) -> List[Page]:
        """Add structured elements and TextBlocks to pages.

        Steps:
        1. Group segments into blocks (split on double newlines)
        2. Collect source nodes and TextBlock info for each block
        3. Generate IDs and augment HTML
        4. Create Element and TextBlock objects
        5. Attach to pages
        """
        from sec2md.models import TextBlock

        # Build elements for each page, tracking their nodes and TextBlocks
        page_elements: Dict[int, List[Element]] = {}
        page_text_blocks: Dict[int, List[TextBlock]] = {}
        block_nodes_map: Dict[str, List[Tag]] = {}

        for page in pages:
            page_num = page.number
            segments = self.page_segments.get(page_num, [])

            if not segments:
                page_elements[page_num] = []
                page_text_blocks[page_num] = []
                continue

            # Group segments into blocks (returns (Element, nodes, text_block) tuples)
            blocks_with_nodes = self._group_segments_into_blocks(segments, page_num)

            # Merge small blocks into larger semantic units
            merged_blocks = self._merge_small_blocks(blocks_with_nodes, page_num, min_chars=500)

            # Separate elements, nodes, and group by TextBlock
            elements = []
            text_block_map: Dict[str, List[str]] = {}  # TextBlock name -> element IDs

            for element, nodes, text_block_info in merged_blocks:
                elements.append(element)
                block_nodes_map[element.id] = nodes

                # Track which TextBlock this element belongs to
                if text_block_info:
                    tb_name = text_block_info.name
                    if tb_name not in text_block_map:
                        text_block_map[tb_name] = []
                    text_block_map[tb_name].append(element.id)

            page_elements[page_num] = elements

            # Create TextBlock objects with actual Element objects
            text_blocks = []
            # Group by name to get unique TextBlocks with their titles
            seen_names = {}
            for element, nodes, text_block_info in merged_blocks:
                if text_block_info and text_block_info.name not in seen_names:
                    seen_names[text_block_info.name] = text_block_info

            # Build element ID to Element map
            element_map = {elem.id: elem for elem in elements}

            for tb_name, tb_info in seen_names.items():
                element_ids = text_block_map.get(tb_name, [])
                if element_ids:
                    # Get actual Element objects
                    tb_elements = [element_map[eid] for eid in element_ids if eid in element_map]
                    text_blocks.append(TextBlock(
                        name=tb_name,
                        title=tb_info.title,
                        elements=tb_elements
                    ))

            page_text_blocks[page_num] = text_blocks

        # Augment HTML with IDs
        self._augment_html_with_ids(page_elements, block_nodes_map)

        # Attach elements and TextBlocks to pages
        result = []
        for page in pages:
            elements = page_elements.get(page.number, [])
            text_blocks = page_text_blocks.get(page.number, [])
            result.append(Page(
                number=page.number,
                content=page.content,
                elements=elements if elements else None,
                text_blocks=text_blocks if text_blocks else None
            ))

        return result

    def _is_bold_header(self, element: Element) -> bool:
        """Check if element is a bold header (main section marker).

        Bold headers start with ** and contain only a short title (< 50 chars typically).
        Example: **Services**, **Competition**, **Markets and Distribution**
        """
        content = element.content.strip()

        # Check if content starts and ends with **
        if not (content.startswith('**') and '**' in content[2:]):
            return False

        # Extract the bold part
        first_line = content.split('\n')[0].strip()

        # Bold headers are typically short and standalone
        # If the first line is entirely bold and short, it's likely a header
        if first_line.startswith('**') and first_line.endswith('**'):
            bold_text = first_line[2:-2].strip()
            # Bold headers are typically < 50 chars and don't contain much punctuation
            if len(bold_text) < 50 and bold_text.count('.') <= 1:
                return True

        return False

    def _merge_small_blocks(
        self,
        blocks_with_nodes: List[Tuple[Element, List[Tag], Optional[TextBlockInfo]]],
        page_num: int,
        min_chars: int = 500
    ) -> List[Tuple[Element, List[Tag], Optional[TextBlockInfo]]]:
        """Merge consecutive small blocks into larger semantic units.

        Rules:
        - Tables always stay separate
        - Bold headers (**text**) start new sections
        - TextBlock boundaries always flush
        - Merge consecutive blocks until min_chars threshold
        - Regenerate IDs for merged blocks

        Args:
            blocks_with_nodes: List of (Element, nodes, text_block) tuples
            page_num: Page number for ID generation
            min_chars: Minimum characters per block (default: 500)

        Returns:
            List of merged (Element, nodes, text_block) tuples
        """
        if not blocks_with_nodes:
            return []

        merged = []
        current_elements = []
        current_nodes = []
        current_chars = 0
        current_text_block = None

        def flush(block_idx: int):
            nonlocal current_elements, current_nodes, current_chars
            if not current_elements:
                return

            # Merge content from all elements
            merged_content = '\n\n'.join(e.content for e in current_elements)

            # Infer kind from merged elements
            kinds = [e.kind for e in current_elements]
            if 'table' in kinds:
                kind = 'table'
            elif 'header' in kinds:
                kind = 'section'
            else:
                kind = current_elements[0].kind

            # Generate new ID
            block_id = self._generate_block_id(page_num, block_idx, merged_content, kind)

            merged_element = Element(
                id=block_id,
                content=merged_content,
                kind=kind,
                page_start=page_num,
                page_end=page_num
            )

            merged.append((merged_element, list(current_nodes), current_text_block))
            current_elements = []
            current_nodes = []
            current_chars = 0

        for i, (element, nodes, text_block) in enumerate(blocks_with_nodes):
            # Check if TextBlock changed - this is a hard boundary, always flush
            text_block_changed = False
            if current_text_block is not None or text_block is not None:
                # Compare TextBlock names (None != anything)
                if current_text_block is None and text_block is not None:
                    text_block_changed = True
                elif current_text_block is not None and text_block is None:
                    text_block_changed = True
                elif current_text_block is not None and text_block is not None:
                    text_block_changed = current_text_block.name != text_block.name

            if text_block_changed and current_elements:
                flush(len(merged))

            # Update current TextBlock
            current_text_block = text_block

            # Check if this is a table
            if element.kind == 'table':
                # If we have accumulated text AND it's small (< min_chars), merge it with the table
                # This handles captions/headers before tables
                if current_elements and current_chars < min_chars:
                    # Merge caption with table
                    current_elements.append(element)
                    current_nodes.extend([n for n in nodes if n not in current_nodes])
                    flush(len(merged))
                else:
                    # Flush current, then add table separately
                    flush(len(merged))
                    merged.append((element, nodes, text_block))
                continue

            # Check if this is a bold header (main section break)
            is_bold_header = self._is_bold_header(element)

            # If we hit a bold header and have content, flush before starting new section
            # BUT: never flush if current content is ONLY headers (headers need content)
            if is_bold_header and current_elements:
                # Check if ALL current elements are headers (no actual content)
                all_headers = all(self._is_bold_header(e) for e in current_elements)
                is_current_only_headers = all_headers and current_chars < 200

                if not is_current_only_headers:
                    flush(len(merged))

            # Add to current merge group
            current_elements.append(element)
            current_nodes.extend([n for n in nodes if n not in current_nodes])
            current_chars += element.char_count

            # Decide whether to flush
            # IMPORTANT: Never flush if current block is only headers - headers need content
            should_flush = False

            # Flush if we've hit min_chars (paragraph is big enough)
            if current_chars >= min_chars:
                should_flush = True

            # OR flush if next element is a bold header (section boundary)
            if i + 1 < len(blocks_with_nodes):
                next_element, _, _ = blocks_with_nodes[i + 1]
                if self._is_bold_header(next_element):
                    should_flush = True

            # OR flush if we're at the end
            if i == len(blocks_with_nodes) - 1:
                should_flush = True

            if should_flush:
                # Check if ALL current elements are headers (no actual content)
                all_headers = all(self._is_bold_header(e) for e in current_elements)
                is_only_headers = all_headers and current_chars < 200

                if not is_only_headers:
                    flush(len(merged))

        # Flush remaining
        if current_elements:
            flush(len(merged))

        return merged

    def _group_segments_into_blocks(self, segments: List[Tuple[str, Optional[Tag], Optional[TextBlockInfo]]], page_num: int) -> List[Tuple[Element, List[Tag], Optional[TextBlockInfo]]]:
        """Group sequential segments into semantic blocks.

        Returns:
            List of (Element, nodes, text_block) tuples
        """
        blocks = []
        current_block_segments = []
        current_block_nodes = []
        current_text_block = None
        block_idx = 0

        for content, node, text_block in segments:
            # Check if this is a block boundary (double newline)
            if content == "\n":
                # Check if previous segment was also a newline
                if current_block_segments and current_block_segments[-1] == "\n":
                    # Double newline - flush current block
                    if len(current_block_segments) > 1:  # Has content beyond the trailing newline
                        block = self._create_block(
                            current_block_segments[:-1],  # Exclude trailing newline
                            current_block_nodes,
                            page_num,
                            block_idx
                        )
                        if block:
                            blocks.append((block, list(current_block_nodes), current_text_block))
                            block_idx += 1
                    current_block_segments = []
                    current_block_nodes = []
                    current_text_block = None
                    continue

            current_block_segments.append(content)
            if node is not None and node not in current_block_nodes:
                current_block_nodes.append(node)
            # Track TextBlock (use last non-None value)
            if text_block is not None:
                current_text_block = text_block

        # Flush remaining block
        if current_block_segments:
            # Remove trailing newlines
            while current_block_segments and current_block_segments[-1] == "\n":
                current_block_segments.pop()

            if current_block_segments:
                block = self._create_block(
                    current_block_segments,
                    current_block_nodes,
                    page_num,
                    block_idx
                )
                if block:
                    blocks.append((block, list(current_block_nodes), current_text_block))

        return blocks

    def _create_block(
        self,
        segments: List[str],
        nodes: List[Tag],
        page_num: int,
        block_idx: int
    ) -> Optional[Element]:
        """Create an Element from segments and nodes."""
        content = "".join(segments).strip()
        if not content:
            return None

        # Infer block kind from nodes
        kind = self._infer_kind_from_nodes(nodes)

        # Generate stable ID
        block_id = self._generate_block_id(page_num, block_idx, content, kind)

        return Element(
            id=block_id,
            content=content,
            kind=kind,
            page_start=page_num,
            page_end=page_num
        )

    def _infer_kind_from_nodes(self, nodes: List[Tag]) -> str:
        """Infer block kind from DOM nodes."""
        if not nodes:
            return "text"

        # Check first meaningful node
        for node in nodes:
            if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                return "header"
            elif node.name == "table":
                return "table"
            elif node.name in {"ul", "ol"}:
                return "list"
            elif node.name == "p":
                return "paragraph"

        return "text"

    def _generate_block_id(self, page: int, idx: int, content: str, kind: str) -> str:
        """Generate stable block ID using normalized content hash."""
        # Normalize: collapse whitespace for stable hashing
        normalized = re.sub(r'\s+', ' ', content.strip()).lower()
        hash_part = hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:8]
        kind_prefix = kind[0] if kind else "b"
        return f"sec2md-p{page}-{kind_prefix}{idx}-{hash_part}"

    def _augment_html_with_ids(self, page_elements: Dict[int, List[Element]], block_nodes_map: Dict[str, List[Tag]]) -> None:
        """Add id attributes and data-sec2md-block to DOM nodes.

        Args:
            page_elements: Map of page_num -> List[Element]
            block_nodes_map: Map of element.id -> List[Tag] (the nodes for that element)
        """
        seen_pages = set()

        # Augment HTML
        for page_num in sorted(page_elements.keys()):
            elements = page_elements[page_num]

            for i, element in enumerate(elements):
                nodes = block_nodes_map.get(element.id, [])
                if not nodes:
                    continue

                first_node = nodes[0]

                # Add page ID to first block on this page
                if page_num not in seen_pages:
                    # Add page-N as an additional ID on the first node
                    if 'id' in first_node.attrs:
                        # Node already has an ID, add page ID as a class instead
                        existing_classes = first_node.get('class', [])
                        if isinstance(existing_classes, str):
                            existing_classes = existing_classes.split()
                        existing_classes.append(f"page-{page_num}")
                        first_node['class'] = existing_classes
                    else:
                        first_node['id'] = f"page-{page_num}"
                    seen_pages.add(page_num)

                # Add block ID to first node (if it doesn't already have page ID)
                if 'id' not in first_node.attrs:
                    first_node['id'] = element.id

                # Add data attribute to all nodes for highlighting
                for node in nodes:
                    node['data-sec2md-block'] = element.id

    def markdown(self) -> str:
        """Get full document as markdown string."""
        pages = self.get_pages()
        return "\n\n".join(page.content for page in pages if page.content)

    def html(self) -> str:
        """Get the HTML with augmented anchors and data attributes.

        Note: Call get_pages(include_elements=True) first to augment the HTML.
        If called before get_pages(), returns the original unmodified HTML.
        """
        return str(self.soup)
