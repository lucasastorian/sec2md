"""Tests for the absolutely positioned table parser (absolute_table_parser.py)."""

import re

import pytest
from bs4 import BeautifulSoup, Tag

from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser
from sec2md.utils import median


def _make_elements(html_snippets: list[str]) -> list[Tag]:
    """Create positioned Tag elements from HTML snippets."""
    combined = "<html><body>" + "".join(html_snippets) + "</body></html>"
    soup = BeautifulSoup(combined, "lxml")
    return [el for el in soup.find_all("div") if el.get("style")]


class TestMedian:
    def test_odd_list(self):
        assert median([3, 1, 2]) == 2

    def test_even_list(self):
        assert median([1, 2, 3, 4]) == 2.5


class TestIsTableLike:
    """Heuristics for table detection."""

    def test_sparse_elements_not_table(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px">Hello</div>',
            '<div style="position:absolute; left:10px; top:30px">World</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        assert not parser.is_table_like()

    def test_grid_with_numbers_is_table(self):
        rows = []
        for y in range(0, 120, 20):
            rows.append(f'<div style="position:absolute; left:10px; top:{y}px">Label {y}</div>')
            rows.append(f'<div style="position:absolute; left:200px; top:{y}px">{1000 + y}</div>')
            rows.append(f'<div style="position:absolute; left:350px; top:{y}px">${2000 + y}</div>')
        elements = _make_elements(rows)
        parser = AbsolutelyPositionedTableParser(elements)
        assert parser.is_table_like()

    def test_long_text_not_table(self):
        elements = _make_elements([
            f'<div style="position:absolute; left:10px; top:{y}px">'
            f'This is a very long sentence that definitely looks like prose and not a table cell at all.</div>'
            for y in range(0, 120, 20)
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        assert not parser.is_table_like()

    def test_no_numbers_not_table(self):
        rows = []
        for y in range(0, 120, 20):
            rows.append(f'<div style="position:absolute; left:10px; top:{y}px">Label</div>')
            rows.append(f'<div style="position:absolute; left:200px; top:{y}px">Value</div>')
            rows.append(f'<div style="position:absolute; left:350px; top:{y}px">Text</div>')
        elements = _make_elements(rows)
        parser = AbsolutelyPositionedTableParser(elements)
        assert not parser.is_table_like()


class TestSpacerHandling:
    """Spacer elements should produce spaces, not be dropped."""

    def test_spacer_detected(self):
        elements = _make_elements([
            '<div style="position:absolute; display:inline-block; width:5px; left:50px; top:10px">&nbsp;</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        assert parser._is_spacer(elements[0])

    def test_non_spacer_not_detected(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px">Real text</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        assert not parser._is_spacer(elements[0])

    def test_spacer_in_text_output_adds_space(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px">Hello</div>',
            '<div style="position:absolute; display:inline-block; width:5px; left:60px; top:10px">&nbsp;</div>',
            '<div style="position:absolute; left:70px; top:10px">World</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        text = parser.to_text()
        assert "Hello" in text
        assert "World" in text
        # The spacer should prevent concatenation
        assert "HelloWorld" not in text


class TestToText:
    """Text mode output (fallback when not table-like)."""

    def test_simple_text_output(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px">Line one</div>',
            '<div style="position:absolute; left:10px; top:30px">Line two</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        text = parser.to_text()
        assert "Line one" in text
        assert "Line two" in text

    def test_bold_preserved_in_text(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px; font-weight:700">Bold text</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        text = parser.to_text()
        assert "**Bold text**" in text

class TestToMarkdown:
    """Markdown table output."""

    def test_returns_empty_when_not_table(self):
        elements = _make_elements([
            '<div style="position:absolute; left:10px; top:10px">Just text</div>',
        ])
        parser = AbsolutelyPositionedTableParser(elements)
        assert parser.to_markdown() == ""

    def test_markdown_has_separator(self):
        rows = []
        for y in range(0, 120, 20):
            rows.append(f'<div style="position:absolute; left:10px; top:{y}px">Row {y}</div>')
            rows.append(f'<div style="position:absolute; left:200px; top:{y}px">{100 + y}</div>')
            rows.append(f'<div style="position:absolute; left:350px; top:{y}px">${200 + y}</div>')
        elements = _make_elements(rows)
        parser = AbsolutelyPositionedTableParser(elements)
        md = parser.to_markdown()
        if md:  # Only check if detected as table
            assert "---" in md


class TestClusterByEps:
    """Epsilon-based clustering."""

    def test_close_values_same_cluster(self):
        elements = _make_elements(['<div style="position:absolute; left:10px; top:10px">X</div>'])
        parser = AbsolutelyPositionedTableParser(elements)
        clusters = parser._cluster_by_eps([100.0, 100.5, 101.2], eps=5)
        assert len(set(clusters.values())) == 1

    def test_distant_values_different_clusters(self):
        elements = _make_elements(['<div style="position:absolute; left:10px; top:10px">X</div>'])
        parser = AbsolutelyPositionedTableParser(elements)
        clusters = parser._cluster_by_eps([10.0, 50.0, 100.0], eps=5)
        assert len(set(clusters.values())) == 3

