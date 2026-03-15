"""Tests for section extraction (section_extractor.py and sections.py)."""

import pytest

from sec2md.section_extractor import SectionExtractor, ITEM_PATTERN, PART_PATTERN
from sec2md.sections import extract_sections, get_section
from sec2md.models import Page, Section, Item10K, Item10Q, Item13D, Item13G


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


class TestSectionExtractor13D:
    """SC 13D section extraction."""

    def _make_pages(self, contents: list[str]) -> list[Page]:
        return [Page(number=i + 1, content=c) for i, c in enumerate(contents)]

    def test_single_13d_item(self):
        pages = self._make_pages([
            "**Item 1. Security and Issuer.**\n\nThis relates to common stock."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert sections[0].item == "ITEM 1"

    def test_all_seven_items(self):
        pages = self._make_pages([
            (
                "**Item 1. Security and Issuer.**\n\nIssuer info.\n\n"
                "**Item 2. Identity and Background.**\n\nIdentity info.\n\n"
                "**Item 3. Source of Funds.**\n\nFunds info.\n\n"
                "**Item 4. Purpose of Transaction.**\n\nPurpose info.\n\n"
                "**Item 5. Interest in Securities.**\n\nInterest info.\n\n"
                "**Item 6. Contracts.**\n\nContracts info.\n\n"
                "**Item 7. Exhibits.**\n\nExhibit A."
            )
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert items == [f"ITEM {i}" for i in range(1, 8)]

    def test_items_across_pages(self):
        pages = self._make_pages([
            "**Item 1. Security and Issuer.**\n\nIssuer info.",
            "Continued issuer discussion.",
            "**Item 2. Identity and Background.**\n\nIdentity info."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert "ITEM 1" in items
        assert "ITEM 2" in items
        # Item 1 should span pages 1-2
        item1 = [s for s in sections if s.item == "ITEM 1"][0]
        assert item1.page_range == (1, 2)

    def test_stops_at_signature(self):
        pages = self._make_pages([
            "**Item 1. Security and Issuer.**\n\nContent.\n\n**SIGNATURE**\n\nSigned by someone."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert "SIGNATURE" not in sections[0].markdown()

    def test_skips_content_before_first_item(self):
        pages = self._make_pages([
            "SCHEDULE 13D\n\nCover page boilerplate.",
            "**Item 1. Security and Issuer.**\n\nActual content."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert sections[0].item == "ITEM 1"

    def test_skips_table_rows(self):
        pages = self._make_pages([
            "| Item 1 | Security and Issuer | 5 |\n\n**Item 1. Security and Issuer.**\n\nContent."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert sections[0].item == "ITEM 1"

    def test_no_parts(self):
        pages = self._make_pages([
            "**Item 4. Purpose of Transaction.**\n\nContent."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert sections[0].part is None

    def test_rejects_invalid_item_numbers(self):
        pages = self._make_pages([
            "**Item 1. Security and Issuer.**\n\nContent.\n\n"
            "**Item 10. Something else.**\n\nNot a valid 13D item."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13D")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert "ITEM 1" in items
        assert "ITEM 10" not in items


class TestSectionExtractor13G:
    """SC 13G section extraction."""

    def _make_pages(self, contents: list[str]) -> list[Page]:
        return [Page(number=i + 1, content=c) for i, c in enumerate(contents)]

    def test_13g_items_4_through_10(self):
        pages = self._make_pages([
            (
                "**Item 4 Ownership**\n\nOwnership data.\n\n"
                "**Item 5 Ownership of Five Percent or Less of a Class**\n\nN/A.\n\n"
                "**Item 6 Ownership of More than Five Percent**\n\nN/A.\n\n"
                "**Item 7 Subsidiary Classification**\n\nN/A.\n\n"
                "**Item 8 Group Members**\n\nN/A.\n\n"
                "**Item 9 Notice of Dissolution**\n\nN/A.\n\n"
                "**Item 10 Certification**\n\nI certify."
            )
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13G")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert items == [f"ITEM {i}" for i in range(4, 11)]

    def test_sub_items_grouped(self):
        """Item 1(a) and Item 1(b) should merge into single ITEM 1."""
        pages = self._make_pages([
            (
                "**Item 1(a) Name of Issuer**\n\nAcme Corp\n\n"
                "**Item 1(b) Address**\n\n123 Main St\n\n"
                "**Item 2(a) Name of Person Filing**\n\nJohn Doe"
            )
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13G")
        sections = extractor.get_sections()
        items = [s.item for s in sections]
        assert items.count("ITEM 1") == 1
        assert items.count("ITEM 2") == 1
        # Item 1 content should include both sub-items
        item1 = [s for s in sections if s.item == "ITEM 1"][0]
        assert "Acme Corp" in item1.markdown()
        assert "123 Main St" in item1.markdown()

    def test_accepts_item_10(self):
        """Item 10 is valid for 13G but not 13D."""
        pages = self._make_pages([
            "**Item 10 Certification**\n\nI certify this is correct."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13G")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert sections[0].item == "ITEM 10"

    def test_stops_at_signature(self):
        pages = self._make_pages([
            "**Item 10 Certification**\n\nCertified.\n\n**SIGNATURE**\n\nSigned."
        ])
        extractor = SectionExtractor(pages, filing_type="SC 13G")
        sections = extractor.get_sections()
        assert len(sections) == 1
        assert "SIGNATURE" not in sections[0].markdown()


class TestGetSection13D:
    """get_section with Item13D and Item13G enums."""

    def _make_13d_sections(self) -> list[Section]:
        return [
            Section(part=None, item="ITEM 1", item_title="Security and Issuer",
                    pages=[Page(number=1, content="Issuer content")]),
            Section(part=None, item="ITEM 4", item_title="Purpose of Transaction",
                    pages=[Page(number=2, content="Purpose content")]),
            Section(part=None, item="ITEM 7", item_title="Exhibits",
                    pages=[Page(number=3, content="Exhibit content")]),
        ]

    def test_get_by_13d_enum(self):
        sections = self._make_13d_sections()
        result = get_section(sections, Item13D.PURPOSE_OF_TRANSACTION, filing_type="SC 13D")
        assert result is not None
        assert result.item == "ITEM 4"

    def test_get_by_string(self):
        sections = self._make_13d_sections()
        result = get_section(sections, "ITEM 7", filing_type="SC 13D")
        assert result is not None
        assert result.item == "ITEM 7"

    def test_wrong_filing_type_raises(self):
        sections = self._make_13d_sections()
        with pytest.raises(ValueError):
            get_section(sections, Item13D.EXHIBITS, filing_type="10-K")

    def test_get_by_13g_enum(self):
        sections = [
            Section(part=None, item="ITEM 4", item_title="Ownership",
                    pages=[Page(number=1, content="Ownership data")]),
            Section(part=None, item="ITEM 10", item_title="Certification",
                    pages=[Page(number=2, content="Cert")]),
        ]
        result = get_section(sections, Item13G.OWNERSHIP, filing_type="SC 13G")
        assert result is not None
        assert result.item == "ITEM 4"

    def test_13g_wrong_filing_type_raises(self):
        sections = [
            Section(part=None, item="ITEM 4", item_title="Ownership",
                    pages=[Page(number=1, content="Data")]),
        ]
        with pytest.raises(ValueError):
            get_section(sections, Item13G.OWNERSHIP, filing_type="SC 13D")


class TestItem13DEnum:
    """Item13D and Item13G enum values."""

    def test_13d_has_seven_items(self):
        assert len(Item13D) == 7

    def test_13d_values(self):
        assert Item13D.SECURITY_AND_ISSUER.value == "1"
        assert Item13D.EXHIBITS.value == "7"

    def test_13g_has_ten_items(self):
        assert len(Item13G) == 10

    def test_13g_values(self):
        assert Item13G.SECURITY_AND_ISSUER.value == "1"
        assert Item13G.CERTIFICATION.value == "10"
