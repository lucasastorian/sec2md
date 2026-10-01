"""Tests for the HTML parser (parser.py)."""

import re

import pytest

from sec2md.parser import Parser, _is_absolute, _style, _top_px
from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser
from sec2md.models import Page


class TestParserBasics:
    """Core parsing behavior."""

    def test_simple_paragraph(self):
        parser = Parser("<html><body><p>Hello world</p></body></html>")
        pages = parser.get_pages(include_elements=False)
        assert len(pages) == 1
        assert "Hello world" in pages[0].content

    def test_multiple_paragraphs(self):
        parser = Parser("<html><body><p>Para one</p><p>Para two</p></body></html>")
        pages = parser.get_pages(include_elements=False)
        content = pages[0].content
        assert "Para one" in content
        assert "Para two" in content

    def test_nested_bold_italic(self):
        parser = Parser("<html><body><p><b><i>Bold italic</i></b></p></body></html>")
        pages = parser.get_pages(include_elements=False)
        assert "***Bold italic***" in pages[0].content

    def test_unordered_list(self):
        html = "<html><body><ul><li>Item A</li><li>Item B</li></ul></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        content = pages[0].content
        assert "- Item A" in content
        assert "- Item B" in content

    def test_ordered_list(self):
        html = "<html><body><ol><li>First</li><li>Second</li></ol></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        content = pages[0].content
        assert "1. First" in content
        assert "2. Second" in content

    def test_hidden_element_excluded(self):
        html = '<html><body><p>Visible</p><div style="display:none">Hidden</div></body></html>'
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert "Hidden" not in pages[0].content

    def test_nbsp_cleaned(self):
        html = "<html><body><p>Hello\u00a0world</p></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert "\u00a0" not in pages[0].content

    def test_zero_width_chars_cleaned(self):
        html = "<html><body><p>Hello\u200bworld</p></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert "\u200b" not in pages[0].content


class TestPageSplitting:
    """CSS page-break handling."""

    def test_break_before_always(self):
        html = """<html><body>
        <p>Page 1</p>
        <div style="page-break-before:always"><p>Page 2</p></div>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert len(pages) == 2

    def test_break_after_always(self):
        html = """<html><body>
        <div style="page-break-after:always"><p>Page 1</p></div>
        <p>Page 2</p>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert len(pages) == 2

    def test_css_break_before_page(self):
        html = """<html><body>
        <p>Page 1</p>
        <div style="break-before:page"><p>Page 2</p></div>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert len(pages) == 2

    def test_multiple_breaks(self):
        html = """<html><body>
        <p>Page 1</p>
        <div style="page-break-before:always"><p>Page 2</p></div>
        <div style="page-break-before:always"><p>Page 3</p></div>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert len(pages) == 3

    def test_page_numbers_sequential(self):
        html = """<html><body>
        <p>Content A</p>
        <div style="page-break-before:always"><p>Content B</p></div>
        <div style="page-break-before:always"><p>Content C</p></div>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert pages[0].number == 1
        assert pages[1].number == 2
        assert pages[2].number == 3


class TestBreadcrumbStripping:
    """PART/ITEM breadcrumbs at page tops should be removed."""

    def test_strips_part_item_breadcrumb(self):
        content = "PART II\n\nItem 7\n\nActual content here"
        result = Parser._strip_page_breadcrumbs(content)
        assert "Actual content" in result
        assert result.startswith("Actual")

    def test_preserves_item_with_title(self):
        content = "PART II\n\nITEM 7. Management Discussion\n\nContent"
        result = Parser._strip_page_breadcrumbs(content)
        # Item with title is a real section header, not a breadcrumb
        assert "PART II" in result

    def test_preserves_non_breadcrumb_content(self):
        content = "Some regular content\nMore content"
        result = Parser._strip_page_breadcrumbs(content)
        assert result == content

    def test_strips_bold_wrapped_breadcrumb(self):
        content = "**PART I**\n\n**ITEM 1**\n\nActual content"
        result = Parser._strip_page_breadcrumbs(content)
        assert result.startswith("Actual")


class TestElementExtraction:
    """Element extraction from parsed pages."""

    def test_elements_have_ids(self):
        html = "<html><body><p>Paragraph one</p><p>Paragraph two</p></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=True)
        elements = pages[0].elements
        assert elements is not None
        for elem in elements:
            assert elem.id

    def test_elements_have_content(self):
        html = "<html><body><p>Some content here</p></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=True)
        assert any("Some content" in e.content for e in pages[0].elements)

    def test_element_ids_are_unique(self):
        html = "<html><body><p>A</p><p>B</p><p>C</p></body></html>"
        parser = Parser(html)
        pages = parser.get_pages(include_elements=True)
        ids = [e.id for e in pages[0].elements]
        assert len(ids) == len(set(ids))

    def test_table_element_kind(self):
        html = """<html><body>
        <table><tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></table>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=True)
        table_elements = [e for e in pages[0].elements if e.kind == "table"]
        assert len(table_elements) >= 1

    def test_element_page_numbers(self):
        html = """<html><body>
        <p>Page 1</p>
        <div style="page-break-before:always"><p>Page 2</p></div>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=True)
        for page in pages:
            if page.elements:
                for elem in page.elements:
                    assert elem.page_start == page.number


class TestDisplayPageDetection:
    """Display page number extraction."""

    def _make_parser(self):
        return Parser("<html><body></body></html>")

    def test_validate_sequence_needs_five_pairs(self):
        candidates = [(1, 1), (2, 2), (3, 3)]
        assert self._make_parser()._validate_page_number_sequence(candidates) is False

    def test_validate_sequence_accepts_increasing(self):
        candidates = [(i, i + 10) for i in range(1, 10)]
        assert self._make_parser()._validate_page_number_sequence(candidates) is True

    def test_validate_sequence_rejects_decreasing(self):
        candidates = [(i, 100 - i) for i in range(1, 10)]
        assert self._make_parser()._validate_page_number_sequence(candidates) is False


class TestOneRowTable:
    """Single-row tables should be flattened to text."""

    def test_item_header_table(self):
        html = """<html><body>
        <table><tr><td>Item 1.</td><td>Business</td></tr></table>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        content = pages[0].content
        assert "ITEM 1" in content
        assert "Business" in content

    def test_part_header_table(self):
        html = """<html><body>
        <table><tr><td>Part II</td></tr></table>
        </body></html>"""
        parser = Parser(html)
        pages = parser.get_pages(include_elements=False)
        assert "PART II" in pages[0].content


class TestSpacerPreservation:
    """Regression: spacer divs with &nbsp; must not be dropped before table parsing."""

    def test_extract_positioned_children_includes_spacers(self):
        html = """<html><body>
        <div style="position:relative">
            <div style="position:absolute; left:10px; top:10px">Hello</div>
            <div style="position:absolute; display:inline-block; width:5px; left:60px; top:10px">&nbsp;</div>
            <div style="position:absolute; left:70px; top:10px">World</div>
        </div>
        </body></html>"""
        parser = Parser(html)
        container = parser.soup.find("div", style=re.compile("position:relative"))
        children = parser._extract_absolutely_positioned_children(container)
        assert len(children) == 3, f"Expected 3 children (including spacer), got {len(children)}"


def _tag(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml").body.contents[0]


class TestPrintLayout:
    """Regressions from print-layout filings (2026 S-1s): pt units, CSS custom
    properties, normal-flow bodies beside positioned bands, per-page containers."""

    def test_custom_property_is_not_absolute_positioning(self):
        assert not _is_absolute(_style(_tag('<div style="--position:absolute">x</div>')))
        assert _is_absolute(_style(_tag('<div style="left:0;position: absolute">x</div>')))
        assert _is_absolute(_style(_tag('<div style="position:absolute">x</div>')))

    def test_top_in_pt_is_normalized_to_px(self):
        assert _top_px(_tag('<div style="top:72pt">x</div>')) == pytest.approx(96.0)
        assert _top_px(_tag('<div style="top:96px">x</div>')) == 96.0

    def test_normal_flow_body_beside_positioned_bands_is_kept(self):
        html = """<html><body><div>
          <div style="position:absolute;top:10px;left:10px">HEADER BAND</div>
          <div><p>The body paragraph of the page.</p></div>
          <div style="position:absolute;top:900px;left:10px">FOOTER BAND</div>
        </div></body></html>"""
        content = Parser(html).get_pages(include_elements=False)[0].content
        assert "The body paragraph of the page." in content
        assert content.index("The body paragraph") < content.index("HEADER BAND")

    def test_content_visibility_container_is_a_page(self):
        page = ('<div style="content-visibility:auto;position:relative">'
                '<div style="position:absolute;top:10px;left:10px">{}</div></div>')
        html = f"<html><body>{page.format('First page text')}{page.format('Second page text')}</body></html>"
        pages = Parser(html).get_pages(include_elements=False)
        assert [p.content.strip() for p in pages] == ["First page text", "Second page text"]

    def test_margin_top_is_not_top(self):
        assert _top_px(_tag('<div style="margin-top:0pt;position:absolute;top:72pt">x</div>')) == pytest.approx(96.0)


class TestHtmlComments:
    """Regression: comments are strings to bs4 and were rendered as page text."""

    def test_comments_are_not_content(self):
        html = ("<html><body><p>Hello<!-- Field: Page; Sequence: 4 --> world</p>"
                "<!-- Field: Set; Name: xdx; ID: xdx_01 --><div><b>Bold<!-- x --></b></div></body></html>")
        content = Parser(html).get_pages(include_elements=False)[0].content
        assert "Field" not in content and "xdx" not in content
        assert "Hello world" in content and "**Bold**" in content

    def test_comment_inside_a_word_does_not_split_it(self):
        content = Parser("<html><body><p>F-<!-- Field: Page; Sequence: 1 -->1</p></body></html>").get_pages()[0].content
        assert content.strip() == "F-1"


class TestBreaksInsideTables:
    """Regression: page breaks inside a table (per-page footer tables:
    page number | <p page-break-after> | TOC link) collapsed the filing to one page."""

    FOOTER = ('<table><tr><td>{n}</td></tr><tr><td><p style="page-break-after: always"></p></td></tr>'
              '<tr><td><a href="#toc">Table of Contents</a></td></tr></table>')

    def test_footer_table_break_starts_new_page(self):
        html = ("<html><body><p>Page one body.</p>" + self.FOOTER.format(n=1) +
                "<p>Page two body.</p>" + self.FOOTER.format(n=2) + "<p>Page three body.</p></body></html>")
        pages = Parser(html).get_pages(include_elements=False)
        assert len(pages) == 3
        assert "Page one body." in pages[0].content and "Page two body." not in pages[0].content
        assert "Page two body." in pages[1].content
        assert "Page three body." in pages[2].content

    def test_table_without_breaks_stays_on_page(self):
        html = "<html><body><table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table><p>after</p></body></html>"
        assert len(Parser(html).get_pages(include_elements=False)) == 1
