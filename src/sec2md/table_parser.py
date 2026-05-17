from __future__ import annotations

import re
import logging
from bs4 import Tag
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

BULLETS = {"•", "●", "◦", "–", "-", "—", "·", ""}


@dataclass
class Cell:
    """A single cell in a table, potentially containing XBRL data"""
    text: str
    rowspan: int = 1
    colspan: int = 1

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def __repr__(self) -> str:
        return f"Cell(text={self.text!r}, rowspan={self.rowspan}, colspan={self.colspan})"


class GridCell:
    """A cell in the final grid, possibly part of a spanning cell"""

    def __init__(self, cell: Cell, is_spanning: bool = False):
        self.cell = cell
        self.is_spanning = is_spanning

    @property
    def text(self) -> str:
        return self.cell.text

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def __repr__(self) -> str:
        return f"GridCell(cell={self.cell!r}, is_spanning={self.is_spanning})"


class TableParser:
    """A table within a filing document"""

    def __init__(self, table_element: Tag):
        """
        Initialize table from a BS4 table tag

        Args:
            table_element: The specific table BS4 tag
        """
        if not isinstance(table_element, Tag) or table_element.name != 'table':
            raise ValueError("table_element must be a table tag")
        logger.debug("Initializing TableParser for table element")
        self.table_element = table_element

        self.cells = self._extract_cells()
        self.grid = self._create_grid()

    def _extract_cells(self) -> List[List[Cell]]:
        rows = []
        for tr in self.table_element.find_all('tr'):
            row = []
            for td in tr.find_all(['td', 'th']):
                text = td.get_text(separator=" ", strip=True).replace('\xa0', ' ')
                if not text:
                    if td.find('img'):
                        logger.debug("Found image in cell, replacing with bullet")
                        text = '●'  # or '•' depending on your BULLETS set
                rowspan = self._safe_parse_int(td.get('rowspan'))
                colspan = self._safe_parse_int(td.get('colspan'))
                row.append(Cell(text=text, rowspan=rowspan, colspan=colspan))
            if row:
                rows.append(row)
        return rows or [[Cell(text="")]]

    @staticmethod
    def _safe_parse_int(value: str, default: int = 1) -> int:
        """Safely parse an integer value, returning default if parsing fails"""
        try:
            if not value or not isinstance(value, str): # if value is not a string or empty
                return default
            cleaned = ''.join(c for c in value if c.isdigit()) # only keep digits
            return int(cleaned) if cleaned else default
        except (ValueError, TypeError):
            return default

    def _create_grid(self) -> List[List[GridCell]]:
        """Create grid with spanning cells handled"""
        if not self.cells:
            return []

        # Calculate grid dimensions
        max_cols = max(sum(cell.colspan for cell in row) for row in self.cells)
        grid = [[None for _ in range(max_cols)] for _ in range(len(self.cells))]

        for i, row in enumerate(self.cells):
            col = 0
            for cell in row:
                # Find next empty cell
                while col < max_cols and grid[i][col] is not None:
                    col += 1

                if col >= max_cols:
                    break

                grid[i][col] = GridCell(cell)

                for r in range(cell.rowspan):
                    for c in range(cell.colspan):
                        if r == 0 and c == 0:  # Skip main cell
                            continue
                        ri, ci = i + r, col + c
                        if ri < len(grid) and ci < max_cols:
                            grid[ri][ci] = GridCell(cell, is_spanning=True)

                col += cell.colspan

        grid = self._clean_grid(grid)
        logger.debug(f"Grid cleaned: {len(grid)} rows x {len(grid[0]) if grid else 0} cols")
        grid = self._merge_grid(grid)
        logger.debug(f"Grid merged: {len(grid)} rows x {len(grid[0]) if grid else 0} cols")

        return grid

    def _should_merge_cells(self, val1: Optional[GridCell], val2: Optional[GridCell]) -> bool:
        """Check if two cells should be merged based on the rules"""
        # Handle missing cells
        if not val1 or not val2:
            logger.debug("Merging due to missing cell(s)")
            return True

        s1 = val1.text.strip()
        s2 = val2.text.strip()

        # UNIT CONFLICT CHECK: absolute priority
        # Don't merge if one cell has $ and the other has %
        if ('$' in s1 and '%' in s2) or ('%' in s1 and '$' in s2):
            return False

        # Spanning cells should always be allowed to merge with their source column
        # UNLESS there was a unit conflict (checked above)
        if val2.is_spanning:
            return True

        if not s1 or not s2: # at least one cell is empty
            logger.debug(f"Merging due to empty cell: s1='{s1}', s2='{s2}'")
            return True

        if s1 == s2:
            return True

        if self.is_footnote(s2):
            logger.debug(f"Merging due to footnote: {s2}")
            return True

        if s1 == '$':
            # Don't merge dollar sign if the target cell already has a percentage
            if '%' in s2:
                return False
            return True

        if s2 == '%':
            # Don't merge percentage sign if the source cell already has a dollar sign
            if '$' in s1:
                return False
            return True

        if s1 == '(' or s2 == ')':
            return True
            #return False

        return False

    @staticmethod
    def is_footnote(text: str) -> bool:
        """Check if string is a number or letter within square brackets and nothing else, e.g., [1], [b]"""
        pattern = r'^\[[a-zA-Z0-9]+\]$'
        return bool(re.match(pattern, text))

    @staticmethod
    def _clean_grid(grid: List[List[GridCell]]) -> List[List[GridCell]]:
        """Drop rows and columns that contain only empty cells (no text and no XBRL data)"""
        if not grid:
            return grid

        rows_to_keep = [
            i for i, row in enumerate(grid)
            # keep a row if cell is not empty
            if any( 
                cell is not None and cell.text.strip()
                for cell in row
            )
        ]

        columns_to_keep = [
            j for j in range(len(grid[0]))
            if any(
                grid[i][j] is not None and
                (grid[i][j].text.strip())
                for i in range(len(grid))
            )
        ]

        filtered_grid = [
            [grid[i][j] for j in columns_to_keep]
            for i in rows_to_keep
        ]

        return filtered_grid

    def _merge_grid(self, grid: List[List[GridCell]]) -> List[List[GridCell]]:
        """Merge columns in one clean pass"""
        if not grid or not grid[0]:
            return grid

        result = []
        current_col = None

        for col_idx in range(len(grid[0])):
            col = [row[col_idx] for row in grid]

            if current_col is None:
                current_col = col
                continue

            # Only use data rows (index 1+) for deciding whether to merge columns.
            # This ensures headers don't accidentally prevent merging of related columns
            # (like currency symbol and value) while also not forcing unrelated columns to merge.
            should_merge = all(self._should_merge_cells(current_col[i], col[i]) for i in range(1, len(grid)))

            if should_merge:
                logger.debug(f"Merging column {col_idx} into current column")
                merged = []
                for c1, c2 in zip(current_col, col):
                    if not c1 or not c1.text.strip():
                        merged.append(c2)
                    elif not c2 or not c2.text.strip():
                        merged.append(c1)
                    elif c1.text.strip() == c2.text.strip():
                        merged.append(c1)
                    else:
                        text = f"{c1.text} {c2.text}".strip()
                        merged_cell = Cell(text=text)
                        merged.append(GridCell(merged_cell))
                current_col = merged
            else:
                result.append(current_col)
                current_col = col

        if current_col is not None:
            result.append(current_col)

        return list(map(list, zip(*result)))

    def to_matrix(self) -> List[List[str]]:
        """Convert grid to text matrix"""
        return [[cell.text if cell else "" for cell in row] for row in self.grid]

    def _normalize_text(self, text: str) -> str:
        """Normalize text while preserving deliberate blanks"""
        if text is None:
            return ""
        return str(text).replace("\xa0", " ").strip()

    def _process_headers(self, matrix: List[List[str]]) -> tuple[List[str], List[List[str]]]:
        """
        Process table headers with robust multi-row fusion.
        """
        if not matrix or len(matrix) < 1:
            return [], []

        nrows = len(matrix)
        ncols = len(matrix[0]) if matrix else 0
        logger.debug(f"Processing headers for matrix: {nrows} rows x {ncols} cols")

        # Identify how many rows are headers
        header_rows = 0
        for i in range(min(5, nrows)): # check up to 5 rows
            row = [self._normalize_text(v) for v in matrix[i]]
            
            # A row is likely a header if it's mostly non-numeric and has many blanks/dups
            blanks_or_dups = sum(1 for j in range(ncols) if not row[j] or (j > 0 and row[j] == row[j-1]))
            is_numeric = sum(1 for cell in row if re.search(r'\d', cell))
            
            # Heuristic: 
            # - Row 0 is always a header
            # - Row i is a header if it has very few numeric values (< 25% of columns)
            #   or if it has many blanks/dups and few numeric values.
            if i == 0 or is_numeric < max(1, ncols // 4) or (blanks_or_dups >= max(1, ncols // 3) and is_numeric < max(1, ncols // 2)):
                header_rows = i + 1
            else:
                break
        
        logger.debug(f"Identified {header_rows} header rows")
            
        # Fuse the header rows
        fused = [""] * ncols
        for i in range(header_rows):
            row = [self._normalize_text(v) for v in matrix[i]]
            for j in range(ncols):
                text = row[j]
                if text:
                    if not fused[j]:
                        fused[j] = text
                    elif text not in fused[j]: # avoid duplication from spanning cells
                        # Handle unit conflict (e.g., adding $ to a header that has % or "Percent")
                        current = fused[j]
                        has_percent = '%' in current or 'Percent' in current or 'percentage' in current.lower()
                        has_dollar = '$' in current or 'Dollar' in current or 'dollar' in current.lower()
                        
                        if '$' in text and has_percent:
                            # Strip percent markers
                            current = current.replace('%', '').replace('Percentage', '').replace('percentage', '').replace('Percent', '').replace('percent', '').strip()
                        elif '%' in text and has_dollar:
                            # Strip dollar markers
                            current = current.replace('$', '').replace('Dollar', '').replace('dollar', '').strip()
                        
                        if text not in current:
                            fused[j] = f"{current} {text}".strip()
                        else:
                            fused[j] = current.strip()
        
        # Clean up any leftover duplicates and extra spaces
        fused = [re.sub(r'\s+', ' ', f).strip() for f in fused]
        
        return fused, matrix[header_rows:]

    def _clean_empty_rows_and_cols(self, headers: List[str], data: List[List[str]]) -> tuple[List[str], List[List[str]]]:
        """Remove completely empty rows and columns"""
        if not data:
            return headers, data

        ncols = len(headers)

        # Remove empty rows
        cleaned_data = [row for row in data if any(self._normalize_text(cell) for cell in row)]

        if not cleaned_data:
            return headers, []

        # Identify empty columns
        cols_with_content = set()
        for row in cleaned_data:
            for j, cell in enumerate(row):
                if j < ncols and self._normalize_text(cell):
                    cols_with_content.add(j)

        # Keep columns with content
        if not cols_with_content:
            return [], []

        cols_to_keep = sorted(cols_with_content)
        new_headers = [headers[j] for j in cols_to_keep if j < len(headers)]
        new_data = [[row[j] if j < len(row) else "" for j in cols_to_keep] for row in cleaned_data]

        return new_headers, new_data

    def _looks_like_list_table(self) -> bool:
        """Special case - some quirky files format lists as tables"""
        if len(self.cells) != 1:
            return False
        row = self.cells[0]
        texts = [c.text.strip() for c in row]
        has_bullet = any(t in BULLETS for t in texts)
        has_payload = any(t for t in texts[1:])
        return has_bullet and has_payload

    def to_markdown(self) -> str:
        """
        Convert table to markdown format.

        Returns:
            Markdown table string
        """
        # Special-case list tables
        if self._looks_like_list_table():
            row = self.cells[0]
            payload = ""
            for c in reversed(row):
                t = c.text.strip()
                if t and t not in BULLETS:
                    payload = t
                    break
            return f"- {payload}" if payload else ""

        # Get the matrix
        matrix = self.to_matrix()
        if not matrix:
            logger.debug("Table matrix is empty, skipping")
            return ""

        # Process headers
        headers, data = self._process_headers(matrix)
        logger.debug(f"Headers identified: {headers}")
        logger.debug(f"Data rows remaining: {len(data)}")
        
        # Clean empty rows/columns
        headers, data = self._clean_empty_rows_and_cols(headers, data)
        logger.debug(f"After cleaning: {len(headers)} cols, {len(data)} rows")

        if not headers and not data:
            logger.debug("Table is empty after cleaning, skipping")
            return ""

        # Build markdown table
        lines = []

        # Header row
        if headers:
            escaped_headers = [str(h).replace("|", "\\|") for h in headers]
            lines.append("| " + " | ".join(escaped_headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Data rows
        for row in data:
            # Pad row to match header length
            while len(row) < len(headers):
                row.append("")
            # Escape pipe characters
            escaped_row = [str(cell).replace("|", "\\|") for cell in row[:len(headers)]]
            lines.append("| " + " | ".join(escaped_row) + " |")

        return "\n".join(lines)

    def md(self) -> str:
        """Alias for to_markdown() for backwards compatibility"""
        return self.to_markdown()
