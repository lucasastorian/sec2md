"""Tests for data models (models.py)."""

from unittest.mock import patch, MagicMock

import pytest

from sec2md.models import (
    Page, Section, Element, TextBlock,
    Item10K, Item10Q, Item8K, FilingType,
    ITEM_10K_MAPPING, ITEM_10Q_MAPPING, ITEM_8K_TITLES,
    _count_tokens,
)


class TestCountTokens:
    def test_returns_positive_for_text(self):
        assert _count_tokens("hello world") >= 1

    def test_fallback_on_tiktoken_error(self):
        """Regression: tiktoken runtime errors must not crash token counting."""
        mock_tiktoken = MagicMock()
        mock_tiktoken.get_encoding.side_effect = ConnectionError("offline")
        with patch.dict("sys.modules", {"tiktoken": mock_tiktoken}):
            with patch("sec2md.models.TIKTOKEN_AVAILABLE", True):
                result = _count_tokens("hello world")
                assert result == max(1, len("hello world") // 4)


class TestElement:
    def test_char_count_and_tokens(self):
        elem = Element(id="e1", content="Hello world", kind="paragraph", page_start=1, page_end=1)
        assert elem.char_count == 11
        assert elem.tokens >= 1


class TestPage:
    def test_tokens_computed(self):
        page = Page(number=1, content="Some content here")
        assert page.tokens >= 1

    def test_to_dict(self):
        page = Page(number=1, content="Content")
        d = page.to_dict()
        assert d["number"] == 1
        assert d["content"] == "Content"

    def test_to_dict_essentials_excludes_extras(self):
        page = Page(number=1, content="Content", display_page=42)
        d = page.to_dict(include_only_essentials=True)
        assert "number" in d
        assert "content" in d
        assert "display_page" not in d

    def test_elements_dict(self):
        elem = Element(id="e1", content="C", kind="paragraph", page_start=1, page_end=1)
        page_with = Page(number=1, content="C", elements=[elem])
        assert page_with.elements_dict is not None
        assert len(page_with.elements_dict) == 1

        page_without = Page(number=2, content="C")
        assert page_without.elements_dict is None


class TestSection:
    def test_requires_pages(self):
        with pytest.raises(ValueError, match="at least one page"):
            Section(part="PART I", item="ITEM 1", pages=[])

    def test_page_range(self):
        pages = [Page(number=3, content="A"), Page(number=5, content="B")]
        section = Section(part="PART I", item="ITEM 1", pages=pages)
        assert section.page_range == (3, 5)

    def test_tokens(self):
        pages = [Page(number=1, content="Some content")]
        section = Section(part="PART I", item="ITEM 1", pages=pages)
        assert section.tokens >= 1

    def test_content_has_delimiters_markdown_does_not(self):
        pages = [Page(number=1, content="Page 1"), Page(number=2, content="Page 2")]
        section = Section(part="PART I", item="ITEM 1", pages=pages)
        assert "---" in section.content
        assert "---" not in section.markdown()


class TestTextBlock:
    def test_element_ids(self):
        elem = Element(id="e1", content="C", kind="paragraph", page_start=1, page_end=1)
        tb = TextBlock(name="us-gaap:Test", elements=[elem])
        assert tb.element_ids == ["e1"]

    def test_page_span_fields(self):
        tb = TextBlock(
            name="test", elements=[],
            start_page=5, end_page=8, source_pages=[5, 6, 7, 8]
        )
        assert tb.start_page == 5
        assert tb.end_page == 8
        assert len(tb.source_pages) == 4


class TestEnums:
    def test_item_values(self):
        assert Item10K.RISK_FACTORS.value == "1A"
        assert Item10Q.FINANCIAL_STATEMENTS_P1.value == "1.P1"
        assert Item8K.OTHER_EVENTS.value == "8.01"

    def test_mappings_complete(self):
        for item in Item10K:
            assert item in ITEM_10K_MAPPING
        for item in Item10Q:
            assert item in ITEM_10Q_MAPPING
        for item in Item8K:
            assert item.value in ITEM_8K_TITLES


class TestFilingType:
    def test_all_types_present(self):
        from typing import get_args
        args = get_args(FilingType)
        assert set(args) == {"10-K", "10-Q", "20-F", "8-K", "SC 13D", "SC 13G"}


class TestVersionConsistency:
    """Regression: __init__.py version must match pyproject.toml."""

    def test_version_matches_pyproject(self):
        import sec2md
        import tomllib
        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        assert sec2md.__version__ == pyproject["project"]["version"]
