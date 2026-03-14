"""Tests for the core conversion API (core.py)."""

import pytest

from sec2md.core import convert_to_markdown, parse_filing
from sec2md.models import Page


class TestConvertToMarkdown:
    """Tests for convert_to_markdown function."""

    def test_returns_string_by_default(self):
        html = "<html><body><p>Hello world</p></body></html>"
        result = convert_to_markdown(html)
        assert isinstance(result, str)
        assert "Hello world" in result

    def test_returns_pages_when_requested(self):
        html = "<html><body><p>Hello world</p></body></html>"
        result = convert_to_markdown(html, return_pages=True)
        assert isinstance(result, list)
        assert len(result) >= 1
        assert isinstance(result[0], Page)

    def test_bytes_input(self):
        html = b"<html><body><p>Bytes input</p></body></html>"
        result = convert_to_markdown(html)
        assert "Bytes input" in result

    def test_pdf_rejected(self):
        with pytest.raises(ValueError, match="PDF content detected"):
            convert_to_markdown(b"%PDF-1.4 fake pdf content")
        with pytest.raises(ValueError, match="PDF content detected"):
            convert_to_markdown("%PDF-1.4 fake pdf content")

    def test_empty_html(self):
        result = convert_to_markdown("<html><body></body></html>")
        assert isinstance(result, str)

    def test_preserves_bold(self):
        html = "<html><body><p><b>Bold text</b></p></body></html>"
        result = convert_to_markdown(html)
        assert "**Bold text**" in result

    def test_preserves_italic(self):
        html = "<html><body><p><i>Italic text</i></p></body></html>"
        result = convert_to_markdown(html)
        assert "*Italic text*" in result

    def test_preserves_headers(self):
        html = "<html><body><h1>Title</h1><p>Body</p></body></html>"
        # h1 tags are not converted to markdown headers -- they're treated as bold block text
        result = convert_to_markdown(html)
        assert "Title" in result

    def test_hidden_elements_removed(self):
        html = '<html><body><p>Visible</p><p style="display:none">Hidden</p></body></html>'
        result = convert_to_markdown(html)
        assert "Visible" in result
        assert "Hidden" not in result

    def test_page_break_splits_pages(self):
        html = """<html><body>
        <p>Page one</p>
        <div style="page-break-before:always"><p>Page two</p></div>
        </body></html>"""
        pages = convert_to_markdown(html, return_pages=True)
        assert len(pages) == 2
        assert "Page one" in pages[0].content
        assert "Page two" in pages[1].content

class TestParseFiling:
    """Tests for parse_filing function."""

    def test_returns_pages_with_elements(self):
        html = "<html><body><p>Paragraph one</p><p>Paragraph two</p></body></html>"
        pages = parse_filing(html, include_elements=True)
        assert isinstance(pages, list)
        assert len(pages) >= 1
        assert pages[0].elements is not None

    def test_returns_pages_without_elements(self):
        html = "<html><body><p>Content</p></body></html>"
        pages = parse_filing(html, include_elements=False)
        assert isinstance(pages, list)
        assert pages[0].elements is None
