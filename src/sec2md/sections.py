"""Section extraction utilities for SEC filings."""

from typing import List, Optional, Union
from sec2md.models import Page, Section, FilingType, Item10K, Item10Q, Item13D, Item13G, ITEM_10K_MAPPING, ITEM_10Q_MAPPING, ITEM_13D_MAPPING, ITEM_13G_MAPPING
from sec2md.section_extractor import SectionExtractor

# item enum -> (the filing type it belongs to, enum -> (part, item))
_ITEM_ENUMS = {
    Item10K: ("10-K", ITEM_10K_MAPPING),
    Item10Q: ("10-Q", ITEM_10Q_MAPPING),
    Item13D: ("SC 13D", ITEM_13D_MAPPING),
    Item13G: ("SC 13G", ITEM_13G_MAPPING),
}


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
    extractor = SectionExtractor(
        pages=pages,
        filing_type=filing_type,
        debug=debug
    )

    # SectionExtractor now returns Section objects directly
    return extractor.get_sections()


def get_section(
    sections: List[Section],
    item: Union[Item10K, Item10Q, Item13D, Item13G, str],
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
    if type(item) in _ITEM_ENUMS:
        form, mapping = _ITEM_ENUMS[type(item)]
        if filing_type != form:
            raise ValueError(f"{type(item).__name__} enum requires filing_type='{form}', got '{filing_type}'")
        target_part, target_item = mapping[item]
    else:  # "ITEM 1A" or "1A", in any part
        target_item = str(item).upper().strip()
        if not target_item.startswith("ITEM"):
            target_item = f"ITEM {target_item}"
        target_part = None

    return next((s for s in sections if s.item == target_item and target_part in (None, s.part)), None)
