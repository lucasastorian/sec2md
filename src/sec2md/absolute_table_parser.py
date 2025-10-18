from __future__ import annotations

import re
from bs4 import Tag
from collections import defaultdict
from typing import List, Optional, Tuple, Dict

NUMERIC_RE = re.compile(r"""
    ^\s*
    [\(\[]?                      # optional opening paren/bracket
    [\-—–]?\s*                   # optional dash
    [$€£¥]?\s*                   # optional currency
    \d+(?:[.,]\d{3})*           # integer part (with or without thousands)
    (?:[.,]\d+)?                # decimals
    \s*%?                       # optional percent
    [\)\]]?\s*$                 # optional closing paren/bracket
""", re.X)


def median(values: List[float]) -> float:
    """Calculate median of a list of numbers."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
    return sorted_vals[n // 2]


class AbsolutelyPositionedTableParser:
    """
    Parser for pseudo-tables constructed from absolutely positioned div elements.

    These appear in some SEC filings where tables are rendered using position:absolute
    divs instead of proper HTML table elements.
    """

    def __init__(self, elements: List[Tag]):
        """
        Initialize with a list of absolutely positioned elements.

        Args:
            elements: List of Tag elements that are absolutely positioned
        """
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
        """Extract and clean text from an element."""
        text = element.get_text(separator=" ", strip=True)
        text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _is_bold(self, el: Tag) -> bool:
        """Check if element has bold styling."""
        style = (el.get("style") or "").lower()
        return "font-weight:700" in style or "font-weight:bold" in style

    def _is_spacer(self, el: Tag) -> bool:
        """
        Detect inline-block spacer boxes that should be treated as spaces.

        These are common in PDF->HTML conversions: <div style="display:inline-block;width:5px">&nbsp;</div>
        """
        if not isinstance(el, Tag):
            return False

        style = el.get("style", "").lower().replace(" ", "")
        text = el.get_text(strip=True)
        has_nbsp = '\xa0' in str(el) or '&nbsp;' in str(el)
        width_match = re.search(r'width:(\d+)px', style)

        is_inline_block = 'display:inline-block' in style
        is_empty_or_nbsp = (not text or has_nbsp)
        is_narrow = width_match and int(width_match.group(1)) < 30

        return is_inline_block and is_empty_or_nbsp and is_narrow

    def _contains_number(self, text: str) -> bool:
        """Check if text contains a numeric value using robust pattern."""
        return bool(NUMERIC_RE.search(text))

    def _extract_positions(self) -> List[Tuple[float, float, Tag]]:
        """Extract positions for all elements with valid positioning."""
        positioned = []
        for el in self.elements:
            pos = self._get_position(el)

            # Handle spacer boxes - add as synthetic space marker
            if self._is_spacer(el):
                if pos:
                    # Create a synthetic tag that we'll recognize later
                    positioned.append((pos[0], pos[1], el))
                continue

            text = self._clean_text(el)
            # Only include elements with both position and text content
            if pos and text:
                left, top = pos
                positioned.append((left, top, el))
        return positioned

    def _filter_table_content(self, elements: List[Tuple[float, float, Tag]]) -> List[Tuple[float, float, Tag]]:
        """
        Filter out title/caption text that appears before the actual table.

        Tables often have introductory text like "The following table sets forth..."
        This should be excluded from table detection and rendering.
        """
        if len(elements) < 10:
            return elements  # Too small to have significant leading text

        # Group by Y position to find rows
        y_coords = [top for _, top, _ in elements]
        y_clusters = self._cluster_by_eps(y_coords, eps=15)

        # Count elements per row
        row_counts = defaultdict(list)
        for left, top, el in elements:
            row_cluster = y_clusters[top]
            row_counts[row_cluster].append((left, top, el))

        # Sort rows by Y position
        sorted_rows = sorted(row_counts.items(), key=lambda x: min(t for _, t, _ in x[1]))

        # Find the first row with multiple elements (likely start of actual table)
        table_start_row = None
        for row_id, row_elements in sorted_rows:
            if len(row_elements) >= 3:  # Row with at least 3 elements = likely table row
                table_start_row = row_id
                break

        if table_start_row is None:
            return elements  # Couldn't identify table start, return all

        # Get the Y position of the table start
        table_start_y = min(top for _, top, _ in row_counts[table_start_row])

        # Filter out elements that are significantly above the table start (>30px)
        filtered = [(l, t, e) for l, t, e in elements if t >= table_start_y - 30]

        return filtered if len(filtered) >= 6 else elements  # Sanity check

    def _cluster_by_eps(self, values: List[float], eps: float) -> Dict[float, int]:
        """
        Cluster positions within epsilon tolerance.

        This is more robust than gap-based clustering because it handles
        rendering jitter (e.g., 100.0, 100.5, 101.2 should be same cluster).

        Args:
            values: List of coordinate values
            eps: Epsilon tolerance (pixels)

        Returns:
            Dictionary mapping value -> cluster_id
        """
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
        """
        Determine if the positioned elements form a table-like structure.

        This uses multiple heuristics to distinguish actual data tables from
        normal paragraph text that happens to be absolutely positioned.

        Returns:
            True if elements appear to form a table, False otherwise
        """
        if len(self.positioned_elements) < 6:  # Need at least a 2x3 table
            return False

        # Filter out caption/title text
        filtered_elements = self._filter_table_content(self.positioned_elements)

        if len(filtered_elements) < 6:
            return False

        # Extract coordinates from filtered elements
        x_coords = [left for left, _, _ in filtered_elements]
        y_coords = [top for _, top, _ in filtered_elements]

        # Cluster with epsilon tolerance (12px for rows, 50px for columns)
        y_clusters = self._cluster_by_eps(y_coords, eps=12)
        x_clusters = self._cluster_by_eps(x_coords, eps=50)

        n_rows = len(set(y_clusters.values()))
        n_cols = len(set(x_clusters.values()))

        # Need at least 2x3 grid (2 columns minimum)
        if n_rows < 2 or n_cols < 2:
            return False

        # CRITICAL: Check for numeric content - tables should have numbers
        # Use robust numeric pattern
        elements_with_numbers = sum(
            1 for _, _, el in filtered_elements
            if not self._is_spacer(el) and self._contains_number(self._clean_text(el))
        )
        numeric_ratio = elements_with_numbers / len(filtered_elements)

        # At least 20% of cells should contain numbers
        if numeric_ratio < 0.20:
            return False

        # Check average text length - tables have short cell content
        avg_length = sum(len(self._clean_text(el)) for _, _, el in filtered_elements) / len(filtered_elements)

        # If average cell is > 50 characters, probably paragraph text, not a table
        if avg_length > 50:
            return False

        # Check for sentence structures (periods indicating prose)
        text_with_periods = sum(
            1 for _, _, el in filtered_elements
            if '.' in self._clean_text(el) and len(self._clean_text(el)) > 20
        )

        # If >40% of cells have periods and long text, probably prose
        if text_with_periods / len(filtered_elements) > 0.40:
            return False

        # Check density - should be reasonably filled
        expected_cells = n_rows * n_cols
        actual_cells = len(filtered_elements)
        density = actual_cells / expected_cells

        if density < 0.25:  # Less than 25% filled = probably not a table
            return False

        # Check row consistency - rows should have similar number of elements
        row_counts = defaultdict(int)
        for left, top, _ in filtered_elements:
            row_cluster = y_clusters[top]
            row_counts[row_cluster] += 1

        counts = list(row_counts.values())
        if not counts or sum(counts) / len(counts) < 2:
            return False

        # Check for actual column structure - at least one column should have numeric content
        col_elements = defaultdict(list)
        for left, top, element in filtered_elements:
            col_cluster = x_clusters[left]
            col_elements[col_cluster].append(element)

        has_numeric_column = False
        for col_id, elements in col_elements.items():
            if len(elements) >= 2:
                numeric_in_col = sum(
                    1 for el in elements
                    if not self._is_spacer(el) and self._contains_number(self._clean_text(el))
                )
                if numeric_in_col / len(elements) > 0.5:
                    has_numeric_column = True
                    break

        if not has_numeric_column:
            return False

        return True

    def to_grid(self) -> Optional[List[List[List[Tuple[float, float, Tag]]]]]:
        """
        Convert positioned elements to a 2D grid structure.

        Returns:
            2D grid where each cell contains a list of (left, top, element) tuples,
            or None if structure is not table-like
        """
        if not self.is_table_like():
            return None

        # Filter out caption/title text
        filtered_elements = self._filter_table_content(self.positioned_elements)

        # Extract coordinates from filtered elements
        x_coords = [left for left, _, _ in filtered_elements]
        y_coords = [top for _, top, _ in filtered_elements]

        # Cluster with epsilon tolerance
        y_clusters = self._cluster_by_eps(y_coords, eps=12)
        x_clusters = self._cluster_by_eps(x_coords, eps=50)

        n_rows = len(set(y_clusters.values()))
        n_cols = len(set(x_clusters.values()))

        # Build grid dictionary
        grid_dict: Dict[Tuple[int, int], List[Tuple[float, float, Tag]]] = defaultdict(list)

        for left, top, element in filtered_elements:
            row_cluster = y_clusters[top]
            col_cluster = x_clusters[left]

            # Map to 0-based indices
            row_id = sorted(set(y_clusters.values())).index(row_cluster)
            col_id = sorted(set(x_clusters.values())).index(col_cluster)

            grid_dict[(row_id, col_id)].append((left, top, element))

        # Convert to 2D list
        grid = [[[] for _ in range(n_cols)] for _ in range(n_rows)]

        for (row, col), cell_elements in grid_dict.items():
            if row < n_rows and col < n_cols:
                # Sort by horizontal position within cell
                cell_elements.sort(key=lambda x: x[0])
                grid[row][col] = cell_elements

        return grid

    def to_markdown(self) -> str:
        """
        Convert to markdown table format.

        Returns:
            Markdown table string, or empty string if not table-like
        """
        grid = self.to_grid()
        if grid is None:
            return ""

        # Extract text from grid, merging elements in same cell
        text_grid = []
        for row in grid:
            text_row = []
            for cell_elements in row:
                if not cell_elements:
                    text_row.append("")
                else:
                    # Merge all text from elements in this cell
                    texts = []
                    for _, _, element in cell_elements:
                        if self._is_spacer(element):
                            # Spacer box - add a space if we have previous text
                            if texts:
                                texts.append(" ")
                        else:
                            text = self._clean_text(element)
                            if text:
                                # Preserve bold formatting
                                if self._is_bold(element):
                                    text = f"**{text}**"
                                texts.append(text)
                    text_row.append("".join(texts))
            text_grid.append(text_row)

        if not text_grid:
            return ""

        n_cols = len(text_grid[0]) if text_grid else 0

        # Build markdown table
        lines = []
        for i, row in enumerate(text_grid):
            # Pad row to match column count
            while len(row) < n_cols:
                row.append("")
            # Escape pipe characters
            escaped_row = [cell.replace("|", "\\|") for cell in row]
            lines.append("| " + " | ".join(escaped_row) + " |")

            # Add separator after first row (header)
            if i == 0:
                lines.append("| " + " | ".join(["---"] * n_cols) + " |")

        markdown = "\n".join(lines)

        # Clean up the markdown
        return self._clean_markdown_table(markdown)

    def _clean_markdown_table(self, markdown: str) -> str:
        """
        Clean up markdown table by removing junk rows and empty columns.

        Args:
            markdown: Raw markdown table string

        Returns:
            Cleaned markdown table string
        """
        if not markdown:
            return ""

        lines = markdown.strip().split('\n')
        if len(lines) < 3:  # Need at least header, separator, one data row
            return markdown

        # Parse rows
        rows = []
        separator_idx = -1
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split('|')[1:-1]]  # Remove leading/trailing |
            if all(c in ['---', ''] for c in cells):
                separator_idx = i
                rows.append(cells)
            else:
                rows.append(cells)

        if not rows or separator_idx < 0:
            return markdown

        # Identify junk rows (footnotes, page numbers, mostly empty)
        def is_junk_row(row, row_idx):
            if row_idx <= separator_idx:  # Keep header rows
                return False

            # Check if mostly empty
            non_empty = [c for c in row if c and c != '---']
            if len(non_empty) == 0:
                return True
            if len(non_empty) == 1 and len(non_empty[0]) < 5:  # Single short cell (like page number)
                return True

            # Check if it's a footnote (starts with (a), (b), etc.)
            first_non_empty = next((c for c in row if c), "")
            if re.match(r'^\([a-z]\)', first_non_empty):
                return True

            # Check if one very long cell (footnote text) and rest empty
            if len(non_empty) == 1 and len(non_empty[0]) > 100:
                return True

            return False

        # Filter out junk rows
        cleaned_rows = [row for i, row in enumerate(rows) if not is_junk_row(row, i)]

        if not cleaned_rows or len(cleaned_rows) < 3:
            return markdown

        # Identify and remove empty columns
        n_cols = len(cleaned_rows[0])
        col_has_content = [False] * n_cols

        for row_idx, row in enumerate(cleaned_rows):
            if row_idx == separator_idx:  # Skip separator
                continue
            for col_idx, cell in enumerate(row):
                if col_idx < n_cols and cell and cell != '---':
                    col_has_content[col_idx] = True

        # Remove completely empty columns
        cols_to_keep = [i for i in range(n_cols) if col_has_content[i]]

        # Rebuild table with kept columns
        if not cols_to_keep:
            return markdown

        final_rows = []
        for row in cleaned_rows:
            new_row = [row[i] if i < len(row) else "" for i in cols_to_keep]
            final_rows.append(new_row)

        # Rebuild markdown
        result_lines = []
        for i, row in enumerate(final_rows):
            result_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(result_lines)

    def _join_lines(self, prev: str, current: str, gap: float, median_gap: float) -> Tuple[str, bool]:
        """
        Smart line joining with hyphenation handling.

        Args:
            prev: Previous line text
            current: Current line text
            gap: Vertical gap between lines (pixels)
            median_gap: Median line gap in document

        Returns:
            Tuple of (joined_text, should_add_newline)
        """
        # Hyphenated word continuation
        if prev.endswith('-'):
            # Check if it's likely a hyphenated word (next starts with lowercase)
            if current and current[0].islower():
                # Remove hyphen and join directly
                return (prev[:-1] + current, False)
            else:
                # Keep hyphen but join with space (e.g., "end-of-year Statement")
                return (prev + " " + current, False)

        # Check if previous line looks like it continues (no terminal punctuation)
        ends_with_continuation = not prev.rstrip().endswith(('.', '!', '?', ':', ';', ')', ']'))

        # Small gap + continuation = join with space
        if ends_with_continuation and gap < 1.4 * median_gap:
            return (prev + " " + current, False)

        # Otherwise, separate with newline
        return (prev, True)

    def to_text(self) -> str:
        """
        Convert to plain text format (fallback if not table-like).
        Preserves bold formatting and handles hyphenation.

        Returns:
            Text representation with elements sorted by position and formatting preserved
        """
        # Sort by vertical then horizontal position
        sorted_elements = sorted(self.positioned_elements, key=lambda x: (x[1], x[0]))

        # Group by rows (epsilon clustering for Y coordinates)
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
            if last_top is None or abs(top - last_top) <= 5:  # Same row (5px tolerance)
                current_row.append((left, top, element))
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [(left, top, element)]
            last_top = top

        if current_row:
            rows.append(current_row)

        # Convert to text with formatting and hyphenation handling
        lines = []
        for i, row in enumerate(rows):
            # Sort by horizontal position within row
            row.sort(key=lambda x: x[0])
            texts = []
            for _, _, el in row:
                if self._is_spacer(el):
                    # Add space marker
                    if texts:
                        texts.append(" ")
                else:
                    text = self._clean_text(el)
                    if text:
                        # Preserve bold formatting
                        if self._is_bold(el):
                            text = f"**{text}**"
                        texts.append(text)

            if not texts:
                continue

            line = "".join(texts)

            # Determine if we need spacing before this line
            if i == 0:
                # First line - no spacing needed
                lines.append(line)
            else:
                # Check previous line to determine spacing
                prev_row = rows[i - 1]
                prev_y = prev_row[0][1]
                current_y = row[0][1]
                gap = abs(current_y - prev_y)

                # Check if previous line is a continuation
                prev_line = lines[-1] if lines else ""

                # Check if current line is a bold header
                is_header = (
                        any(self._is_bold(el) for _, _, el in row if not self._is_spacer(el)) and
                        all(self._is_bold(el) for _, _, el in row if
                            not self._is_spacer(el) and self._clean_text(el)) and
                        len(line) < 80
                )

                if is_header and not prev_line.endswith('-'):
                    # Add blank line before header
                    lines.append("")
                    lines.append(line)
                else:
                    # Use smart joining
                    joined_text, needs_newline = self._join_lines(prev_line, line, gap, median_line_gap)

                    if needs_newline:
                        # Replace last line with joined text and add current as new line
                        if lines:
                            lines[-1] = joined_text
                        lines.append(line)
                    else:
                        # Replace last line with joined result
                        if lines:
                            lines[-1] = joined_text

        return "\n".join(lines)
