"""Section extraction utilities for SEC filings."""

from typing import List, Optional, Union
from sec2md.models import Page, Section, FilingType, Item10K, Item10Q, ITEM_10K_MAPPING, ITEM_10Q_MAPPING
from sec2md.section_extractor import SectionExtractor


def extract_sections(
    pages: List[Page],
    filing_type: FilingType,
    debug: bool = False
) -> List[Section]:
    """
    Extract sections from filing pages.

    Args:
        pages: List of Page objects from convert_to_markdown(return_pages=True)
        filing_type: Type of filing ("10-K" or "10-Q")
        debug: Enable debug logging

    Returns:
        List of Section objects, each containing pages for that section

    Example:
        >>> pages = sec2md.convert_to_markdown(html, return_pages=True)
        >>> sections = sec2md.extract_sections(pages, filing_type="10-K")
        >>> for section in sections:
        ...     print(f"{section.item}: {section.item_title}")
    """
    # Convert Page objects to dict format for SectionExtractor
    pages_data = [{"page": p.number, "content": p.content} for p in pages]

    extractor = SectionExtractor(
        pages=pages_data,
        filing_type=filing_type,
        debug=debug
    )

    sections_data = extractor.get_sections()

    # Convert back to Section objects with Page objects
    sections = []
    for section_data in sections_data:
        section_pages = [
            Page(number=p["page"], content=p["content"])
            for p in section_data["pages"]
        ]
        sections.append(
            Section(
                part=section_data["part"],
                item=section_data["item"],
                item_title=section_data["item_title"],
                pages=section_pages
            )
        )

    return sections


def get_section(
    sections: List[Section],
    item: Union[Item10K, Item10Q, str],
    filing_type: FilingType = "10-K"
) -> Optional[Section]:
    """
    Get a specific section by item enum or string.

    Args:
        sections: List of sections from extract_sections()
        item: Item enum (Item10K.RISK_FACTORS) or string ("ITEM 1A")
        filing_type: Type of filing ("10-K" or "10-Q")

    Returns:
        Section object if found, None otherwise

    Example:
        >>> sections = sec2md.extract_sections(pages, filing_type="10-K")
        >>> risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
        >>> print(risk.markdown())
    """
    # Map enum to (part, item) tuple
    if isinstance(item, Item10K):
        if filing_type != "10-K":
            raise ValueError(f"Item10K enum requires filing_type='10-K', got '{filing_type}'")
        target_part, target_item = ITEM_10K_MAPPING[item]
    elif isinstance(item, Item10Q):
        if filing_type != "10-Q":
            raise ValueError(f"Item10Q enum requires filing_type='10-Q', got '{filing_type}'")
        target_part, target_item = ITEM_10Q_MAPPING[item]
    else:
        # String format - normalize it
        item_str = str(item).upper().strip()
        if not item_str.startswith("ITEM"):
            item_str = f"ITEM {item_str}"
        target_item = item_str
        target_part = None  # Match any part

    # Find matching section
    for section in sections:
        if section.item == target_item:
            if target_part is None or section.part == target_part:
                return section

    return None
