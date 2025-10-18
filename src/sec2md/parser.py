from __future__ import annotations

import re
import logging
from collections import defaultdict
from typing import List, Dict, Union,  Optional
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser, median
from sec2md.table_parser import TableParser
from sec2md.models import Page

BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "br", "hr", "ul", "ol", "li"}
BOLD_TAGS = {"b", "strong"}
ITALIC_TAGS = {"i", "em"}

_ws = re.compile(r"\s+")
_css_decl = re.compile(r"^[a-zA-Z\-]+\s*:\s*[^;]+;\s*$")
ITEM_HEADER_CELL_RE = re.compile(r"^\s*Item\s+([0-9IVX]+)\.\s*$", re.I)
PART_HEADER_CELL_RE = re.compile(r"^\s*Part\s+([IVX]+)\s*$", re.I)

logger = logging.getLogger(__name__)


class Parser:
    """Document parser with support for regular tables and pseudo-tables."""

    def __init__(self, content: str):
        self.soup = BeautifulSoup(content, "lxml")
        self.includes_table = False
        self.pages: Dict[int, List[str]] = defaultdict(list)
        self.input_char_count = len(self.soup.get_text())

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

    def _append(self, page_num: int, s: str) -> None:
        if s:
            self.pages[page_num].append(s)

    def _blankline_before(self, page_num: int) -> None:
        """Ensure exactly one blank line before the next block."""
        buf = self.pages[page_num]
        if not buf:
            return
        if not buf[-1].endswith("\n"):
            buf.append("\n")
        if len(buf) >= 2 and buf[-1] == "\n" and buf[-2] == "\n":
            return
        buf.append("\n")

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
                    self._append(page_num, markdown_table)
                    self._blankline_after(page_num)
            else:
                # Not a table - group by visual lines and render as text
                text = table_parser.to_text()
                if text:
                    if i > 0:
                        self._blankline_before(page_num)
                    self._append(page_num, text)

        return page_num

    def _stream_pages(self, root: Union[Tag, NavigableString], page_num: int = 1) -> int:
        """Walk the DOM once; split only on CSS break styles."""
        if isinstance(root, Tag) and self._has_break_before(root):
            page_num += 1

        if isinstance(root, NavigableString):
            t = self._process_text_node(root)
            if t:
                self._append(page_num, t + " ")
            return page_num

        if not isinstance(root, Tag):
            return page_num

        if self._is_hidden(root):
            return page_num

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
            return current

        # Inline-display elements should not trigger blocks
        is_inline_display = self._is_inline_display(root)
        is_block = self._is_block(root) and root.name not in {"br",
                                                              "hr"} and not is_inline_display and not is_absolutely_positioned

        if is_block:
            self._blankline_before(page_num)

        # Handle tables and lists atomically
        if root.name in {"table", "ul", "ol"}:
            t = self._process_element(root)
            if t:
                self._append(page_num, t)
            self._blankline_after(page_num)
            if self._has_break_after(root):
                page_num += 1
            return page_num

        # For inline wrappers (bold/italic), render atomically
        wrap = self._wrap_markdown(root)
        if wrap and not is_block:
            t = self._process_element(root)
            if t:
                self._append(page_num, t + " ")
            if self._has_break_after(root):
                page_num += 1
            return page_num

        # Stream children for block elements
        current = page_num
        for child in root.children:
            current = self._stream_pages(child, current)

        if is_block:
            self._blankline_after(current)

        if self._has_break_after(root):
            current += 1

        return current

    def get_pages(self) -> List[Page]:
        """Get parsed pages as Page objects."""
        self.pages = defaultdict(list)
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

            result.append(Page(number=page_num, content=content))

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

    def markdown(self) -> str:
        """Get full document as markdown string."""
        pages = self.get_pages()
        return "\n\n".join(page.content for page in pages if page.content)
