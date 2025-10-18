"""Data models for SEC filing parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Literal, Tuple


# Type alias for filing types
FilingType = Literal["10-K", "10-Q"]


class Item10K(str, Enum):
    """10-K Filing Items - human readable names mapped to item numbers."""

    # Part I
    BUSINESS = "1"
    RISK_FACTORS = "1A"
    UNRESOLVED_STAFF_COMMENTS = "1B"
    CYBERSECURITY = "1C"
    PROPERTIES = "2"
    LEGAL_PROCEEDINGS = "3"
    MINE_SAFETY = "4"

    # Part II
    MARKET_FOR_STOCK = "5"
    SELECTED_FINANCIAL_DATA = "6"  # Removed in recent years
    MD_AND_A = "7"
    MARKET_RISK = "7A"
    FINANCIAL_STATEMENTS = "8"
    CHANGES_IN_ACCOUNTING = "9"
    CONTROLS_AND_PROCEDURES = "9A"
    OTHER_INFORMATION = "9B"
    CYBERSECURITY_DISCLOSURES = "9C"

    # Part III
    DIRECTORS_AND_OFFICERS = "10"
    EXECUTIVE_COMPENSATION = "11"
    SECURITY_OWNERSHIP = "12"
    CERTAIN_RELATIONSHIPS = "13"
    PRINCIPAL_ACCOUNTANT = "14"

    # Part IV
    EXHIBITS = "15"
    FORM_10K_SUMMARY = "16"


class Item10Q(str, Enum):
    """10-Q Filing Items - human readable names with part disambiguation."""

    # Part I
    FINANCIAL_STATEMENTS_P1 = "1.P1"
    MD_AND_A_P1 = "2.P1"
    MARKET_RISK_P1 = "3.P1"
    CONTROLS_AND_PROCEDURES_P1 = "4.P1"

    # Part II
    LEGAL_PROCEEDINGS_P2 = "1.P2"
    RISK_FACTORS_P2 = "1A.P2"
    UNREGISTERED_SALES_P2 = "2.P2"
    DEFAULTS_P2 = "3.P2"
    MINE_SAFETY_P2 = "4.P2"
    OTHER_INFORMATION_P2 = "5.P2"
    EXHIBITS_P2 = "6.P2"


# Internal mappings from enum to (part, item) tuples
ITEM_10K_MAPPING: dict[Item10K, Tuple[str, str]] = {
    # Part I
    Item10K.BUSINESS: ("PART I", "ITEM 1"),
    Item10K.RISK_FACTORS: ("PART I", "ITEM 1A"),
    Item10K.UNRESOLVED_STAFF_COMMENTS: ("PART I", "ITEM 1B"),
    Item10K.CYBERSECURITY: ("PART I", "ITEM 1C"),
    Item10K.PROPERTIES: ("PART I", "ITEM 2"),
    Item10K.LEGAL_PROCEEDINGS: ("PART I", "ITEM 3"),
    Item10K.MINE_SAFETY: ("PART I", "ITEM 4"),

    # Part II
    Item10K.MARKET_FOR_STOCK: ("PART II", "ITEM 5"),
    Item10K.SELECTED_FINANCIAL_DATA: ("PART II", "ITEM 6"),
    Item10K.MD_AND_A: ("PART II", "ITEM 7"),
    Item10K.MARKET_RISK: ("PART II", "ITEM 7A"),
    Item10K.FINANCIAL_STATEMENTS: ("PART II", "ITEM 8"),
    Item10K.CHANGES_IN_ACCOUNTING: ("PART II", "ITEM 9"),
    Item10K.CONTROLS_AND_PROCEDURES: ("PART II", "ITEM 9A"),
    Item10K.OTHER_INFORMATION: ("PART II", "ITEM 9B"),
    Item10K.CYBERSECURITY_DISCLOSURES: ("PART II", "ITEM 9C"),

    # Part III
    Item10K.DIRECTORS_AND_OFFICERS: ("PART III", "ITEM 10"),
    Item10K.EXECUTIVE_COMPENSATION: ("PART III", "ITEM 11"),
    Item10K.SECURITY_OWNERSHIP: ("PART III", "ITEM 12"),
    Item10K.CERTAIN_RELATIONSHIPS: ("PART III", "ITEM 13"),
    Item10K.PRINCIPAL_ACCOUNTANT: ("PART III", "ITEM 14"),

    # Part IV
    Item10K.EXHIBITS: ("PART IV", "ITEM 15"),
    Item10K.FORM_10K_SUMMARY: ("PART IV", "ITEM 16"),
}


ITEM_10Q_MAPPING: dict[Item10Q, Tuple[str, str]] = {
    # Part I
    Item10Q.FINANCIAL_STATEMENTS_P1: ("PART I", "ITEM 1"),
    Item10Q.MD_AND_A_P1: ("PART I", "ITEM 2"),
    Item10Q.MARKET_RISK_P1: ("PART I", "ITEM 3"),
    Item10Q.CONTROLS_AND_PROCEDURES_P1: ("PART I", "ITEM 4"),

    # Part II
    Item10Q.LEGAL_PROCEEDINGS_P2: ("PART II", "ITEM 1"),
    Item10Q.RISK_FACTORS_P2: ("PART II", "ITEM 1A"),
    Item10Q.UNREGISTERED_SALES_P2: ("PART II", "ITEM 2"),
    Item10Q.DEFAULTS_P2: ("PART II", "ITEM 3"),
    Item10Q.MINE_SAFETY_P2: ("PART II", "ITEM 4"),
    Item10Q.OTHER_INFORMATION_P2: ("PART II", "ITEM 5"),
    Item10Q.EXHIBITS_P2: ("PART II", "ITEM 6"),
}


@dataclass
class Page:
    """Represents a single page of markdown content."""

    number: int
    content: str

    def __str__(self) -> str:
        return self.content


@dataclass
class Section:
    """Represents a filing section (e.g., ITEM 1A - Risk Factors)."""

    part: Optional[str]
    item: Optional[str]
    item_title: Optional[str]
    pages: List[Page]

    def markdown(self) -> str:
        """Get section content as single markdown string."""
        return "\n\n".join(p.content for p in self.pages)

    def __str__(self) -> str:
        return self.markdown()

    @property
    def page_range(self) -> Tuple[int, int]:
        """Get the start and end page numbers for this section."""
        if not self.pages:
            return (0, 0)
        return (self.pages[0].number, self.pages[-1].number)
