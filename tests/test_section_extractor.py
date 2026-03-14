"""Tests for section extraction (section_extractor.py and sections.py)."""

import pytest

from sec2md.section_extractor import SectionExtractor, ITEM_PATTERN, PART_PATTERN
from sec2md.sections import extract_sections, get_section
from sec2md.models import Page, Section, Item10K, Item10Q


class TestItemPatternMatching:
    """Regex pattern matching for ITEM headers."""

    def test_basic_item_match(self):
        matches = list(ITEM_PATTERN.finditer("ITEM 1 Business"))
        assert len(matches) == 1
        assert matches[0].group(2) == "1"
        assert "Business" in matches[0].group(3)

    def test_item_with_letter_suffix(self):
        matches = list(ITEM_PATTERN.finditer("ITEM 1A Risk Factors"))
        assert len(matches) == 1
        assert matches[0].group(2) == "1A"

    def test_item_separators(self):
        for text in ["ITEM 7. MD&A", "ITEM 2: Properties", "ITEM 3 - Legal"]:
            matches = list(ITEM_PATTERN.finditer(text))
            assert len(matches) == 1, f"Failed for: {text}"

    def test_items_separated_by_blank_line(self):
        """Regression: \\s* in regex must not consume newlines between items."""
        text = "ITEM 5  Title of five\n\nITEM 8  Title of eight"
        matches = list(ITEM_PATTERN.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(2) == "5"
        assert matches[1].group(2) == "8"

    def test_item_case_insensitive(self):
        matches = list(ITEM_PATTERN.finditer("item 5 Market"))
        assert len(matches) == 1

    def test_item_with_leading_whitespace(self):
        matches = list(ITEM_PATTERN.finditer("   ITEM 1 Business"))
        assert len(matches) == 1

    def test_multiple_items_on_separate_lines(self):
        text = "ITEM 1 Business\nITEM 2 Properties"
        matches = list(ITEM_PATTERN.finditer(text))
        assert len(matches) == 2


class TestPartPatternMatching:
    """Regex pattern matching for PART headers."""

    def test_basic_part(self):
        matches = list(PART_PATTERN.finditer("PART I"))
        assert len(matches) == 1
        assert matches[0].group(1).strip().upper() == "PART I"

    def test_part_roman_numerals(self):
        for numeral in ["I", "II", "III", "IV"]:
            matches = list(PART_PATTERN.finditer(f"PART {numeral}"))
            assert len(matches) == 1, f"Failed for PART {numeral}"

    def test_part_case_insensitive(self):
        matches = list(PART_PATTERN.finditer("part ii"))
        assert len(matches) == 1


class TestSectionExtractorStandard:
    """Standard (10-K/10-Q/20-F) section extraction."""

    def _make_pages(self, contents: list[str]) -> list[Page]:
        return [Page(number=i + 1, content=c) for i, c in enumerate(contents)]

    def test_single_item_extraction(self):
        pages = self._make_pages([
            "ITEM 1 Business\n\nThe company operates globally."
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        assert len(sections) >= 1
        assert sections[0].item == "ITEM 1"

    def test_two_items_same_page(self):
        pages = self._make_pages([
            "ITEM 1 Business\n\nBusiness description.\n\nITEM 2 Properties\n\nProperties info."
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert "ITEM 1" in items
        assert "ITEM 2" in items

    def test_items_across_pages(self):
        pages = self._make_pages([
            "ITEM 1 Business\n\nFirst page of business.",
            "Continued business discussion.",
            "ITEM 1A Risk Factors\n\nRisk factor content."
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert "ITEM 1" in items
        assert "ITEM 1A" in items

    def test_toc_page_skipped(self):
        pages = self._make_pages([
            "ITEM 1 ...... 5\nITEM 2 ...... 10\nITEM 3 ...... 15\nITEM 4 ...... 20",
            "ITEM 1 Business\n\nActual content."
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        # TOC page should be skipped, only real ITEM 1 extracted
        assert len(sections) >= 1
        assert any(s.item == "ITEM 1" for s in sections)

    def test_part_inferred_for_10k(self):
        pages = self._make_pages([
            "ITEM 7 Management Discussion\n\nContent"
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        if sections:
            assert sections[0].part == "PART II"

    def test_empty_pages_no_crash(self):
        pages = self._make_pages(["", "", ""])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        assert sections == []

    def test_breadcrumb_items_skipped(self):
        """Items with no title or breadcrumb-like titles should be skipped."""
        pages = self._make_pages([
            "ITEM 7\n\nITEM 7 Management Discussion\n\nContent here"
        ])
        extractor = SectionExtractor(pages, filing_type="10-K")
        sections = extractor.get_sections()
        # Should have at most 1 section for ITEM 7 (the real one with title)
        item7_sections = [s for s in sections if s.item == "ITEM 7"]
        assert len(item7_sections) <= 1


class TestSectionExtractor8K:
    """8-K section extraction."""

    def _make_pages(self, contents: list[str]) -> list[Page]:
        return [
            Page(number=i + 1, content=c)
            for i, c in enumerate(contents)
        ]

    def test_single_8k_item(self):
        pages = self._make_pages([
            "Cover page content",  # page 1 skipped as boilerplate
            "ITEM 5.02 Departure of Directors\n\nDetails here."
        ])
        extractor = SectionExtractor(pages, filing_type="8-K")
        sections = extractor.get_sections()
        assert len(sections) >= 1
        assert sections[0].item == "ITEM 5.02"

    def test_two_8k_items(self):
        pages = self._make_pages([
            "Cover page",  # skipped
            "ITEM 5.02 Officer Change\n\nDetails.\n\nITEM 9.01 Exhibits\n\nExhibit list."
        ])
        extractor = SectionExtractor(pages, filing_type="8-K")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert "ITEM 5.02" in items
        assert "ITEM 9.01" in items

    def test_8k_normalizes_item_codes(self):
        pages = self._make_pages([
            "Cover",
            "ITEM 5.2 Short code\n\nContent."
        ])
        extractor = SectionExtractor(pages, filing_type="8-K")
        sections = extractor.get_sections()
        if sections:
            # 5.2 should be normalized to 5.02
            assert sections[0].item == "ITEM 5.02"

    def test_8k_items_separated_by_blank_line(self):
        """Regression: 8-K regex must not consume newlines between items."""
        text = "ITEM 5.02  Officer change\n\nITEM 8.01  Other events"
        matches = list(SectionExtractor._ITEM_8K_RE.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(2) == "5.02"
        assert matches[1].group(2) == "8.01"

    def test_8k_boilerplate_detection(self):
        extractor = SectionExtractor([], filing_type="8-K")
        # Page 1 is always boilerplate
        assert extractor._is_8k_boilerplate_page("anything", 1) is True
        # Page with TABLE OF CONTENTS
        assert extractor._is_8k_boilerplate_page("TABLE OF CONTENTS here", 2) is True


class TestGetSection:
    """get_section function for retrieving specific sections."""

    def _make_sections(self) -> list[Section]:
        return [
            Section(
                part="PART I", item="ITEM 1",
                item_title="Business",
                pages=[Page(number=1, content="Business content")]
            ),
            Section(
                part="PART I", item="ITEM 1A",
                item_title="Risk Factors",
                pages=[Page(number=2, content="Risk content")]
            ),
            Section(
                part="PART II", item="ITEM 7",
                item_title="MD&A",
                pages=[Page(number=5, content="MD&A content")]
            ),
        ]

    def test_get_by_enum(self):
        sections = self._make_sections()
        result = get_section(sections, Item10K.RISK_FACTORS, filing_type="10-K")
        assert result is not None
        assert result.item == "ITEM 1A"

    def test_get_by_string(self):
        sections = self._make_sections()
        result = get_section(sections, "ITEM 7", filing_type="10-K")
        assert result is not None
        assert result.item == "ITEM 7"

    def test_get_by_short_string(self):
        sections = self._make_sections()
        result = get_section(sections, "1A", filing_type="10-K")
        assert result is not None
        assert result.item == "ITEM 1A"

    def test_get_nonexistent_returns_none(self):
        sections = self._make_sections()
        result = get_section(sections, "ITEM 99", filing_type="10-K")
        assert result is None

    def test_wrong_enum_type_raises(self):
        sections = self._make_sections()
        with pytest.raises(ValueError):
            get_section(sections, Item10K.BUSINESS, filing_type="10-Q")


class TestExtractSections:
    """extract_sections wrapper function."""

    def test_basic_extraction(self):
        pages = [
            Page(number=1, content="ITEM 1 Business\n\nContent here."),
            Page(number=2, content="ITEM 1A Risk Factors\n\nRisk content."),
        ]
        sections = extract_sections(pages, filing_type="10-K")
        assert len(sections) >= 1

    def test_empty_pages(self):
        sections = extract_sections([], filing_type="10-K")
        assert sections == []
