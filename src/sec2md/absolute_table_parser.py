"""Pseudo-tables laid out with position:absolute divs (PDF-to-HTML conversions, print layouts):
told apart from prose by their geometry, rendered as a markdown table or as text."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from bs4 import Tag

from sec2md.utils import NUMERIC_RE, clean_text, css_px, median


class AbsolutelyPositionedTableParser:
    """Parser for pseudo-tables built from position:absolute divs in some SEC filings."""

    def __init__(self, elements: List[Tag]):
        self.elements = elements
        self._texts: Dict[int, str] = {}
        self._table_like: Optional[bool] = None
        self.positioned_elements = self._extract_positions()

    @staticmethod
    def _get_position(el: Tag) -> Optional[Tuple[float, float]]:
        """(left, top) in px, pt converted. A line with a top but no left (full-width lines in
        print-layout filings) is at left 0."""
        if not isinstance(el, Tag):
            return None
        style = el.get("style", "")
        top = css_px(style, "top")
        if top is None:
            return None
        left = css_px(style, "left")
        return (left if left is not None else 0.0, top)

    def _clean_text(self, element: Tag) -> str:
        key = id(element)
        if key not in self._texts:
            self._texts[key] = clean_text(element.get_text(separator=" ", strip=True))
        return self._texts[key]

    @staticmethod
    def _is_bold(el: Tag) -> bool:
        style = (el.get("style") or "").lower().replace(" ", "")
        return "font-weight:700" in style or "font-weight:bold" in style

    @staticmethod
    def _is_spacer(el) -> bool:
        """An empty (or &nbsp;) inline-block narrower than 30px: a space in PDF-to-HTML output."""
        if not isinstance(el, Tag):
            return False
        style = el.get("style", "").lower().replace(" ", "")
        width = re.search(r"width:(\d+)px", style)
        if "display:inline-block" not in style or not (width and int(width.group(1)) < 30):
            return False
        markup = str(el)
        return not el.get_text(strip=True) or "\xa0" in markup or "&nbsp;" in markup

    def _extract_positions(self) -> List[Tuple[float, float, Tag]]:
        """(left, top, element) for the elements with a position and text (or that are spacers)."""
        positioned = []
        for el in self.elements:
            pos = self._get_position(el)
            if pos and (self._is_spacer(el) or self._clean_text(el)):
                positioned.append((pos[0], pos[1], el))
        return positioned

    def _has_number(self, el: Tag) -> bool:
        return not self._is_spacer(el) and bool(NUMERIC_RE.search(self._clean_text(el)))

    def _join(self, elements: List[Tag]) -> str:
        """The elements' text left to right, bold marked; a spacer is a space between texts."""
        texts: List[str] = []
        for el in elements:
            if self._is_spacer(el):
                if texts:
                    texts.append(" ")
            else:
                text = self._clean_text(el)
                if text:
                    texts.append(f"**{text}**" if self._is_bold(el) else text)
        return "".join(texts)

    def _filter_table_content(self, elements: List[Tuple[float, float, Tag]]) -> List[Tuple[float, float, Tag]]:
        """Drop title/caption lines above the table: it starts at the first row of 3+ elements."""
        if len(elements) < 10:
            return elements

        y_clusters = self._cluster_by_eps([top for _, top, _ in elements], eps=15)
        rows = defaultdict(list)
        for left, top, el in elements:
            rows[y_clusters[top]].append((left, top, el))

        sorted_rows = sorted(rows.values(), key=lambda row: min(t for _, t, _ in row))
        first_row = next((row for row in sorted_rows if len(row) >= 3), None)
        if first_row is None:
            return elements

        table_start_y = min(top for _, top, _ in first_row)
        filtered = [(l, t, e) for l, t, e in elements if t >= table_start_y - 30]
        return filtered if len(filtered) >= 6 else elements

    @staticmethod
    def _cluster_by_eps(values: List[float], eps: float) -> Dict[float, int]:
        """Cluster positions within eps of the cluster's first value (rendering jitter)."""
        clusters = {}
        cluster_id = 0
        anchor = None
        for val in sorted(set(values)):
            if anchor is None:
                anchor = val
            elif val - anchor > eps:
                cluster_id += 1
                anchor = val
            clusters[val] = cluster_id
        return clusters

    def is_table_like(self) -> bool:
        """Do the positioned elements form a table: a grid of short, partly numeric cells?"""
        if self._table_like is None:
            self._table_like = self._looks_like_table()
        return self._table_like

    def _looks_like_table(self) -> bool:
        filtered = self._filter_table_content(self.positioned_elements)
        if len(self.positioned_elements) < 6 or len(filtered) < 6:
            return False

        y_clusters = self._cluster_by_eps([top for _, top, _ in filtered], eps=12)
        x_clusters = self._cluster_by_eps([left for left, _, _ in filtered], eps=50)
        n_rows = len(set(y_clusters.values()))
        n_cols = len(set(x_clusters.values()))
        if n_rows < 2 or n_cols < 2:
            return False

        texts = [self._clean_text(el) for _, _, el in filtered]
        if sum(self._has_number(el) for _, _, el in filtered) / len(filtered) < 0.20:
            return False  # >= 20% of cells should hold numbers
        if sum(len(t) for t in texts) / len(filtered) > 50:
            return False  # cells averaging over 50 chars are prose
        if sum(1 for t in texts if "." in t and len(t) > 20) / len(filtered) > 0.40:
            return False  # mostly sentences
        if len(filtered) / (n_rows * n_cols) < 0.25:
            return False  # a grid at least a quarter full

        row_counts = defaultdict(int)
        for _, top, _ in filtered:
            row_counts[y_clusters[top]] += 1
        if sum(row_counts.values()) / len(row_counts) < 2:
            return False  # rows of two elements or more on average

        columns = defaultdict(list)
        for left, _, el in filtered:
            columns[x_clusters[left]].append(el)
        # at least one column mostly numbers
        return any(sum(self._has_number(el) for el in col) / len(col) > 0.5
                   for col in columns.values() if len(col) >= 2)

    def to_grid(self) -> Optional[List[List[List[Tuple[float, float, Tag]]]]]:
        """Convert positioned elements to a 2D grid, or None if not table-like."""
        if not self.is_table_like():
            return None

        filtered = self._filter_table_content(self.positioned_elements)
        y_clusters = self._cluster_by_eps([top for _, top, _ in filtered], eps=12)
        x_clusters = self._cluster_by_eps([left for left, _, _ in filtered], eps=50)
        row_index = {v: i for i, v in enumerate(sorted(set(y_clusters.values())))}
        col_index = {v: i for i, v in enumerate(sorted(set(x_clusters.values())))}

        grid = [[[] for _ in col_index] for _ in row_index]
        for left, top, el in filtered:
            grid[row_index[y_clusters[top]]][col_index[x_clusters[left]]].append((left, top, el))
        for row in grid:
            for cell in row:
                cell.sort(key=lambda x: x[0])
        return grid

    def to_markdown(self) -> str:
        """Convert to markdown table, or empty string if not table-like."""
        grid = self.to_grid()
        if not grid:
            return ""
        text_grid = [[self._join([el for _, _, el in cell]) for cell in row] for row in grid]

        n_cols = len(text_grid[0])
        lines = []
        for i, row in enumerate(text_grid):
            lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
            if i == 0:
                lines.append("| " + " | ".join(["---"] * n_cols) + " |")
        return self._clean_markdown_table("\n".join(lines))

    @staticmethod
    def _clean_markdown_table(markdown: str) -> str:
        """Remove junk rows (footnotes, page numbers) and empty columns."""
        lines = markdown.strip().split("\n")
        if len(lines) < 3:
            return markdown

        rows = []
        separator_idx = -1
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c in ("---", "") for c in cells):
                separator_idx = i
            rows.append(cells)
        if separator_idx < 0:
            return markdown

        def is_junk_row(row, row_idx):
            if row_idx <= separator_idx:
                return False
            non_empty = [c for c in row if c and c != "---"]
            first_non_empty = next((c for c in row if c), "")
            return (not non_empty or (len(non_empty) == 1 and (len(non_empty[0]) < 5 or len(non_empty[0]) > 100))
                    or re.match(r"^\([a-z]\)", first_non_empty) is not None)

        cleaned_rows = [row for i, row in enumerate(rows) if not is_junk_row(row, i)]
        if len(cleaned_rows) < 3:
            return markdown

        n_cols = len(cleaned_rows[0])
        col_has_content = [False] * n_cols
        for row_idx, row in enumerate(cleaned_rows):
            if row_idx == separator_idx:
                continue
            for col_idx, cell in enumerate(row):
                if col_idx < n_cols and cell and cell != "---":
                    col_has_content[col_idx] = True
        cols_to_keep = [i for i in range(n_cols) if col_has_content[i]]
        if not cols_to_keep:
            return markdown
        return "\n".join("| " + " | ".join(row[i] if i < len(row) else "" for i in cols_to_keep) + " |"
                         for row in cleaned_rows)

    @staticmethod
    def _join_lines(prev: str, current: str, gap: float, median_gap: float) -> Tuple[str, bool]:
        """Join lines with hyphenation handling. Returns (joined_text, should_add_newline)."""
        if prev.endswith("-"):
            if current and current[0].islower():
                return prev[:-1] + current, False
            return prev + " " + current, False
        ends_with_continuation = not prev.rstrip().endswith((".", "!", "?", ":", ";", ")", "]"))
        if ends_with_continuation and gap < 1.4 * median_gap:
            return prev + " " + current, False
        return prev, True

    def to_text(self) -> str:
        """Plain text (when not table-like): lines rejoined across line breaks and hyphenation, bold
        lines on their own as headers."""
        sorted_elements = sorted(self.positioned_elements, key=lambda x: (x[1], x[0]))
        if not sorted_elements:
            return ""

        y_coords = [top for _, top, _ in sorted_elements]
        median_line_gap = median([b - a for a, b in zip(y_coords, y_coords[1:]) if b - a > 1]) \
            if len(y_coords) > 1 else 15.0

        rows = []
        current_row = []
        last_top = None
        for left, top, element in sorted_elements:
            if last_top is None or abs(top - last_top) <= 5:
                current_row.append((left, top, element))
            else:
                rows.append(current_row)
                current_row = [(left, top, element)]
            last_top = top
        rows.append(current_row)

        lines = []
        for i, row in enumerate(rows):
            row.sort(key=lambda x: x[0])
            line = self._join([el for _, _, el in row])
            if not line:
                continue
            if i == 0:
                lines.append(line)
                continue

            gap = abs(row[0][1] - rows[i - 1][0][1])
            prev_line = lines[-1] if lines else ""
            words = [el for _, _, el in row if not self._is_spacer(el)]
            is_header = (any(self._is_bold(el) for el in words)
                         and all(self._is_bold(el) for el in words if self._clean_text(el))
                         and len(line) < 80)
            if is_header and not prev_line.endswith("-"):
                lines.append("")
                lines.append(line)
            else:
                joined_text, needs_newline = self._join_lines(prev_line, line, gap, median_line_gap)
                if lines:
                    lines[-1] = joined_text
                if needs_newline:
                    lines.append(line)
        return "\n".join(lines)
