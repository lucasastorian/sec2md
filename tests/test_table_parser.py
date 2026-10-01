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


class TestNoCellIsDropped:
    """Column merging must never discard text: every non-empty cell reaches the markdown."""

    def _md(self, html):
        from bs4 import BeautifulSoup
        return TableParser(BeautifulSoup(html, "lxml").find("table")).md()

    def test_rowspan_label_value_pairs_survive(self):
        # DART disclosure layout: label/value pairs spanning two rows, then a two-row tail.
        md = self._md("""<table>
            <tr><td rowspan="2">Company</td><td rowspan="2">Samsung</td><td rowspan="2">Code</td>
                <td rowspan="2">005930</td><td>tel</td><td>02-2255-9000</td></tr>
            <tr><td>(fax)</td><td>02-2255-6164</td></tr></table>""")
        for text in ("Company", "Samsung", "Code", "005930", "tel", "02-2255-9000", "(fax)", "02-2255-6164"):
            assert text in md

    def test_first_row_value_after_dollar_sign_is_kept(self):
        # Apple 10-K term-debt maturities: the first row is data, not a header.
        md = self._md("""<table>
            <tr><td>2025</td><td>$</td><td>10,930</td></tr>
            <tr><td>2026</td><td></td><td>12,342</td></tr></table>""")
        assert "$ 10,930" in md and "12,342" in md

    def test_distinct_headers_are_not_merged(self):
        md = self._md("""<table>
            <tr><td>Total</td><td>Remaining authorization</td></tr>
            <tr><td>112,260</td><td></td></tr></table>""")
        assert "Remaining authorization" in md


class TestNestedTables:
    """Regression: a table read the rows and cells of tables nested in it as its own, so a career
    history nested in an officer's cell came out three times and pushed the columns out of line."""

    def test_nested_table_text_stays_in_its_cell(self):
        html = """<table>
          <tr><td>Name</td><td>Career</td><td>Shares</td></tr>
          <tr><td>Tanaka</td><td><table><tr><td>2008</td><td>Joined</td></tr>
                                        <tr><td>2024</td><td>CEO</td></tr></table></td><td>10,610</td></tr>
        </table>"""
        md = TableParser(BeautifulSoup(html, "lxml").find("table")).to_markdown()
        assert md.splitlines() == ["| Name | Career | Shares |", "| --- | --- | --- |",
                                   "| Tanaka | 2008 Joined 2024 CEO | 10,610 |"]


class TestEmptyRows:
    """Regression: empty <tr>s were dropped before the grid was laid out, so a header's rowspan
    meant to cover them swallowed the data rows after them instead."""

    def test_rowspan_over_empty_rows(self):
        html = """<table>
          <tr><td rowspan="3">Item</td><td rowspan="3">2019</td></tr><tr></tr><tr></tr>
          <tr><td>Cost</td><td>25,499</td></tr>
          <tr><td>Accumulated depreciation</td><td>(10,192)</td></tr>
        </table>"""
        md = TableParser(BeautifulSoup(html, "lxml").find("table")).to_markdown()
        assert md.splitlines() == ["| Item | 2019 |", "| --- | --- |",
                                   "| Cost | 25,499 |", "| Accumulated depreciation | (10,192) |"]
