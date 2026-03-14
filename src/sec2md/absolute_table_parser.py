from __future__ import annotations

import re
from bs4 import Tag
from collections import defaultdict
from typing import List, Optional, Tuple, Dict

from sec2md.utils import NUMERIC_RE, median, clean_text


class AbsolutelyPositionedTableParser:
    """Parser for pseudo-tables built from position:absolute divs in some SEC filings."""

    def __init__(self, elements: List[Tag]):
        self.elements = elements
        self.positioned_elements = self._extract_positions()

    def _get_position(self, el: Tag) -> Optional[Tuple[float, float]]:
        """Extract (left, top) position from element style."""
        if not isinstance(el, Tag):
            return None
        style = el.get("style", "")
        left_match = re.search(r'left:\s*(\d+(?:\.\d+)?)px', style)
        top_match = re.search(r'top:\s*(\d+(?:\.\d+)?)px', style)
        if left_match and top_match:
            return (float(left_match.group(1)), float(top_match.group(1)))
        return None

    def _clean_text(self, element: Tag) -> str:
        return clean_text(element.get_text(separator=" ", strip=True))

    def _is_bold(self, el: Tag) -> bool:
        style = (el.get("style") or "").lower()
        return "font-weight:700" in style or "font-weight:bold" in style

    @staticmethod
    def _is_spacer(el) -> bool:
        """Detect inline-block spacer boxes common in PDF->HTML conversions."""
        if not isinstance(el, Tag):
            return False
        style = el.get("style", "").lower().replace(" ", "")
        text = el.get_text(strip=True)
        has_nbsp = '\xa0' in str(el) or '&nbsp;' in str(el)
        width_match = re.search(r'width:(\d+)px', style)
        return (
            'display:inline-block' in style
            and (not text or has_nbsp)
            and bool(width_match and int(width_match.group(1)) < 30)
        )

    def _contains_number(self, text: str) -> bool:
        return bool(NUMERIC_RE.search(text))

    def _extract_positions(self) -> List[Tuple[float, float, Tag]]:
        positioned = []
        for el in self.elements:
            pos = self._get_position(el)
            if self._is_spacer(el):
                if pos:
                    positioned.append((pos[0], pos[1], el))
                continue
            text = self._clean_text(el)
            if pos and text:
                positioned.append((pos[0], pos[1], el))
        return positioned

    def _filter_table_content(self, elements: List[Tuple[float, float, Tag]]) -> List[Tuple[float, float, Tag]]:
        """Filter out title/caption text that appears before the actual table."""
        if len(elements) < 10:
            return elements

        y_coords = [top for _, top, _ in elements]
        y_clusters = self._cluster_by_eps(y_coords, eps=15)

        row_counts = defaultdict(list)
        for left, top, el in elements:
            row_counts[y_clusters[top]].append((left, top, el))

        sorted_rows = sorted(row_counts.items(), key=lambda x: min(t for _, t, _ in x[1]))

        # First row with >= 3 elements is likely the start of the actual table
        table_start_row = None
        for row_id, row_elements in sorted_rows:
            if len(row_elements) >= 3:
                table_start_row = row_id
                break

        if table_start_row is None:
            return elements

        table_start_y = min(top for _, top, _ in row_counts[table_start_row])
        filtered = [(l, t, e) for l, t, e in elements if t >= table_start_y - 30]
        return filtered if len(filtered) >= 6 else elements

    def _cluster_by_eps(self, values: List[float], eps: float) -> Dict[float, int]:
        """Cluster positions within epsilon tolerance to handle rendering jitter."""
        if not values:
            return {}

        sorted_vals = sorted(set(values))
        cluster_id = 0
        clusters = {}
        anchor = sorted_vals[0]

        for val in sorted_vals:
            if val - anchor > eps:
                cluster_id += 1
                anchor = val
            clusters[val] = cluster_id

        return clusters

    def is_table_like(self) -> bool:
        """Determine if positioned elements form a table-like structure."""
        if len(self.positioned_elements) < 6:
            return False

        filtered_elements = self._filter_table_content(self.positioned_elements)
        if len(filtered_elements) < 6:
            return False

        x_coords = [left for left, _, _ in filtered_elements]
        y_coords = [top for _, top, _ in filtered_elements]

        y_clusters = self._cluster_by_eps(y_coords, eps=12)
        x_clusters = self._cluster_by_eps(x_coords, eps=50)

        n_rows = len(set(y_clusters.values()))
        n_cols = len(set(x_clusters.values()))

        if n_rows < 2 or n_cols < 2:
            return False

        # >= 20% of cells should contain numbers
        elements_with_numbers = sum(
            1 for _, _, el in filtered_elements
            if not self._is_spacer(el) and self._contains_number(self._clean_text(el))
        )
        if elements_with_numbers / len(filtered_elements) < 0.20:
            return False

        # Avg cell > 50 chars = probably prose, not a table
        avg_length = sum(len(self._clean_text(el)) for _, _, el in filtered_elements) / len(filtered_elements)
        if avg_length > 50:
            return False

        # > 40% long text with periods = prose
        text_with_periods = sum(
            1 for _, _, el in filtered_elements
            if '.' in self._clean_text(el) and len(self._clean_text(el)) > 20
        )
        if text_with_periods / len(filtered_elements) > 0.40:
            return False

        # Grid should be >= 25% filled
        if len(filtered_elements) / (n_rows * n_cols) < 0.25:
            return False

        # Rows should average >= 2 elements
        row_counts = defaultdict(int)
        for left, top, _ in filtered_elements:
            row_counts[y_clusters[top]] += 1
        counts = list(row_counts.values())
        if not counts or sum(counts) / len(counts) < 2:
            return False

        # At least one column should be predominantly numeric
        col_elements = defaultdict(list)
        for left, top, element in filtered_elements:
            col_elements[x_clusters[left]].append(element)

        has_numeric_column = any(
            sum(1 for el in elems if not self._is_spacer(el) and self._contains_number(self._clean_text(el)))
            / len(elems) > 0.5
            for elems in col_elements.values()
            if len(elems) >= 2
        )
        if not has_numeric_column:
            return False

        return True

    def to_grid(self) -> Optional[List[List[List[Tuple[float, float, Tag]]]]]:
        """Convert positioned elements to a 2D grid, or None if not table-like."""
        if not self.is_table_like():
            return None

        filtered_elements = self._filter_table_content(self.positioned_elements)
        x_coords = [left for left, _, _ in filtered_elements]
        y_coords = [top for _, top, _ in filtered_elements]

        y_clusters = self._cluster_by_eps(y_coords, eps=12)
        x_clusters = self._cluster_by_eps(x_coords, eps=50)

        sorted_row_ids = sorted(set(y_clusters.values()))
        sorted_col_ids = sorted(set(x_clusters.values()))
        row_index = {v: i for i, v in enumerate(sorted_row_ids)}
        col_index = {v: i for i, v in enumerate(sorted_col_ids)}

        n_rows = len(sorted_row_ids)
        n_cols = len(sorted_col_ids)

        grid_dict: Dict[Tuple[int, int], List[Tuple[float, float, Tag]]] = defaultdict(list)
        for left, top, element in filtered_elements:
            row_id = row_index[y_clusters[top]]
            col_id = col_index[x_clusters[left]]
            grid_dict[(row_id, col_id)].append((left, top, element))

        grid = [[[] for _ in range(n_cols)] for _ in range(n_rows)]
        for (row, col), cell_elements in grid_dict.items():
            if row < n_rows and col < n_cols:
                cell_elements.sort(key=lambda x: x[0])
                grid[row][col] = cell_elements

        return grid

    def to_markdown(self) -> str:
        """Convert to markdown table, or empty string if not table-like."""
        grid = self.to_grid()
        if grid is None:
            return ""

        text_grid = []
        for row in grid:
            text_row = []
            for cell_elements in row:
                if not cell_elements:
                    text_row.append("")
                else:
                    texts = []
                    for _, _, element in cell_elements:
                        if self._is_spacer(element):
                            if texts:
                                texts.append(" ")
                        else:
                            text = self._clean_text(element)
                            if text:
                                if self._is_bold(element):
                                    text = f"**{text}**"
                                texts.append(text)
                    text_row.append("".join(texts))
            text_grid.append(text_row)

        if not text_grid:
            return ""

        n_cols = len(text_grid[0])
        lines = []
        for i, row in enumerate(text_grid):
            while len(row) < n_cols:
                row.append("")
            escaped_row = [cell.replace("|", "\\|") for cell in row]
            lines.append("| " + " | ".join(escaped_row) + " |")
            if i == 0:
                lines.append("| " + " | ".join(["---"] * n_cols) + " |")

        return self._clean_markdown_table("\n".join(lines))

    def _clean_markdown_table(self, markdown: str) -> str:
        """Remove junk rows (footnotes, page numbers) and empty columns."""
        if not markdown:
            return ""

        lines = markdown.strip().split('\n')
        if len(lines) < 3:
            return markdown

        rows = []
        separator_idx = -1
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if all(c in ['---', ''] for c in cells):
                separator_idx = i
            rows.append(cells)

        if not rows or separator_idx < 0:
            return markdown

        def is_junk_row(row, row_idx):
            if row_idx <= separator_idx:
                return False
            non_empty = [c for c in row if c and c != '---']
            if len(non_empty) == 0:
                return True
            if len(non_empty) == 1 and len(non_empty[0]) < 5:
                return True
            first_non_empty = next((c for c in row if c), "")
            if re.match(r'^\([a-z]\)', first_non_empty):
                return True
            if len(non_empty) == 1 and len(non_empty[0]) > 100:
                return True
            return False

        cleaned_rows = [row for i, row in enumerate(rows) if not is_junk_row(row, i)]
        if not cleaned_rows or len(cleaned_rows) < 3:
            return markdown

        n_cols = len(cleaned_rows[0])
        col_has_content = [False] * n_cols
        for row_idx, row in enumerate(cleaned_rows):
            if row_idx == separator_idx:
                continue
            for col_idx, cell in enumerate(row):
                if col_idx < n_cols and cell and cell != '---':
                    col_has_content[col_idx] = True

        cols_to_keep = [i for i in range(n_cols) if col_has_content[i]]
        if not cols_to_keep:
            return markdown

        result_lines = []
        for row in cleaned_rows:
            new_row = [row[i] if i < len(row) else "" for i in cols_to_keep]
            result_lines.append("| " + " | ".join(new_row) + " |")

        return "\n".join(result_lines)

    def _join_lines(self, prev: str, current: str, gap: float, median_gap: float) -> Tuple[str, bool]:
        """Join lines with hyphenation handling. Returns (joined_text, should_add_newline)."""
        if prev.endswith('-'):
            if current and current[0].islower():
                return (prev[:-1] + current, False)
            else:
                return (prev + " " + current, False)

        ends_with_continuation = not prev.rstrip().endswith(('.', '!', '?', ':', ';', ')', ']'))
        if ends_with_continuation and gap < 1.4 * median_gap:
            return (prev + " " + current, False)

        return (prev, True)

    def to_text(self) -> str:
        """Convert to plain text (fallback when not table-like). Preserves bold and handles hyphenation."""
        sorted_elements = sorted(self.positioned_elements, key=lambda x: (x[1], x[0]))
        if not sorted_elements:
            return ""

        y_coords = [top for _, top, _ in sorted_elements]
        median_line_gap = median([y_coords[i + 1] - y_coords[i]
                                  for i in range(len(y_coords) - 1)
                                  if y_coords[i + 1] - y_coords[i] > 1]) if len(y_coords) > 1 else 15.0

        rows = []
        current_row = []
        last_top = None

        for left, top, element in sorted_elements:
            if last_top is None or abs(top - last_top) <= 5:
                current_row.append((left, top, element))
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [(left, top, element)]
            last_top = top

        if current_row:
            rows.append(current_row)

        lines = []
        for i, row in enumerate(rows):
            row.sort(key=lambda x: x[0])
            texts = []
            for _, _, el in row:
                if self._is_spacer(el):
                    if texts:
                        texts.append(" ")
                else:
                    text = self._clean_text(el)
                    if text:
                        if self._is_bold(el):
                            text = f"**{text}**"
                        texts.append(text)

            if not texts:
                continue

            line = "".join(texts)

            if i == 0:
                lines.append(line)
            else:
                prev_row = rows[i - 1]
                gap = abs(row[0][1] - prev_row[0][1])
                prev_line = lines[-1] if lines else ""

                is_header = (
                    any(self._is_bold(el) for _, _, el in row if not self._is_spacer(el)) and
                    all(self._is_bold(el) for _, _, el in row if
                        not self._is_spacer(el) and self._clean_text(el)) and
                    len(line) < 80
                )

                if is_header and not prev_line.endswith('-'):
                    lines.append("")
                    lines.append(line)
                else:
                    joined_text, needs_newline = self._join_lines(prev_line, line, gap, median_line_gap)
                    if lines:
                        lines[-1] = joined_text
                    if needs_newline:
                        lines.append(line)

        return "\n".join(lines)
