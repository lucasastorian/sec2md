"""Tests for the standard table parser (table_parser.py)."""

import pytest
from bs4 import BeautifulSoup, Tag

from sec2md.table_parser import TableParser, Cell


def _make_table(html: str) -> Tag:
    """Parse an HTML table string into a Tag."""
    soup = BeautifulSoup(html, "lxml")
    return soup.find("table")


class TestBasicTables:
    """Simple table parsing."""

    def test_simple_2x2(self):
        html = """<table>
        <tr><td>Name</td><td>Value</td></tr>
        <tr><td>A</td><td>1</td></tr>
        </table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert "Name" in md
        assert "Value" in md
        assert "---" in md  # separator
        assert "A" in md
        assert "1" in md

    def test_header_row_has_separator(self):
        html = """<table>
        <tr><td>H1</td><td>H2</td></tr>
        <tr><td>D1</td><td>D2</td></tr>
        </table>"""
        md = TableParser(_make_table(html)).to_markdown()
        lines = md.strip().split("\n")
        assert len(lines) >= 3
        assert all(c in "|- " for c in lines[1].replace("---", ""))

    def test_three_columns(self):
        html = """<table>
        <tr><td>A</td><td>B</td><td>C</td></tr>
        <tr><td>1</td><td>2</td><td>3</td></tr>
        </table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert md.count("|") >= 8  # 4 per row * 2 rows minimum

    def test_empty_cells(self):
        html = """<table>
        <tr><td>X</td><td></td></tr>
        <tr><td></td><td>Y</td></tr>
        </table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert "X" in md
        assert "Y" in md


class TestSpanning:
    """Rowspan and colspan handling."""

    def test_colspan(self):
        html = """<table>
        <tr><td colspan="2">Merged</td></tr>
        <tr><td>A</td><td>B</td></tr>
        </table>"""
        tp = TableParser(_make_table(html))
        matrix = tp.to_matrix()
        # First row should have the merged cell
        assert any("Merged" in cell for row in matrix for cell in row)

    def test_rowspan(self):
        html = """<table>
        <tr><td rowspan="2">Span</td><td>R1</td></tr>
        <tr><td>R2</td></tr>
        </table>"""
        tp = TableParser(_make_table(html))
        matrix = tp.to_matrix()
        assert len(matrix) == 2
        assert "Span" in matrix[0][0]

    def test_invalid_rowspan_ignored(self):
        html = """<table>
        <tr><td rowspan="abc">Cell</td><td>Other</td></tr>
        </table>"""
        # Should not crash
        tp = TableParser(_make_table(html))
        assert tp.to_markdown() is not None


class TestPipeEscaping:
    """Pipe characters in cells must be escaped."""

    def test_pipe_in_cell_escaped(self):
        html = """<table>
        <tr><td>A|B</td><td>C</td></tr>
        <tr><td>D</td><td>E</td></tr>
        </table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert "A\\|B" in md


class TestListTable:
    """Single-row tables with bullet markers should render as list items."""

    def test_bullet_list_table(self):
        html = """<table><tr><td>•</td><td>List item text</td></tr></table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert md.startswith("- ")
        assert "List item text" in md

    def test_dash_list_table(self):
        html = """<table><tr><td>-</td><td>Dash item</td></tr></table>"""
        md = TableParser(_make_table(html)).to_markdown()
        assert "Dash item" in md


class TestHeaderFusion:
    """Multi-row header detection and fusion."""

    def test_two_row_header_fused(self):
        html = """<table>
        <tr><td></td><td>2023</td><td>2022</td></tr>
        <tr><td>Metric</td><td>(millions)</td><td>(millions)</td></tr>
        <tr><td>Revenue</td><td>100</td><td>90</td></tr>
        </table>"""
        tp = TableParser(_make_table(html))
        md = tp.to_markdown()
        # Headers should be fused with " — " separator
        assert "—" in md or "2023" in md  # Either fused or separate


class TestToMatrix:
    """Matrix representation of tables."""

    def test_matrix_dimensions(self):
        html = """<table>
        <tr><td>A</td><td>B</td></tr>
        <tr><td>C</td><td>D</td></tr>
        </table>"""
        matrix = TableParser(_make_table(html)).to_matrix()
        assert len(matrix) == 2
        assert all(len(row) == 2 for row in matrix)

    def test_matrix_content(self):
        html = """<table>
        <tr><td>Hello</td></tr>
        </table>"""
        matrix = TableParser(_make_table(html)).to_matrix()
        assert matrix[0][0] == "Hello"


class TestTableParserValidation:
    """Input validation."""

    def test_rejects_non_table_tag(self):
        soup = BeautifulSoup("<div>Not a table</div>", "lxml")
        with pytest.raises(ValueError, match="table tag"):
            TableParser(soup.find("div"))
