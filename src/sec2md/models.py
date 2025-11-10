"""Data models for SEC filing parsing."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, field_validator, computed_field

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    from IPython.display import display, Markdown as IPythonMarkdown
    IPYTHON_AVAILABLE = True
except ImportError:
    IPYTHON_AVAILABLE = False


def _count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken if available, else char/4 heuristic."""
    if TIKTOKEN_AVAILABLE:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    else:
        return max(1, len(text) // 4)


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


class Item8K(str, Enum):
    """8-K Filing Items - event-driven disclosure items."""

    # Section 1 – Registrant's Business and Operations
    MATERIAL_AGREEMENT = "1.01"
    TERMINATION_OF_AGREEMENT = "1.02"
    BANKRUPTCY = "1.03"
    MINE_SAFETY = "1.04"
    CYBERSECURITY_INCIDENT = "1.05"

    # Section 2 – Financial Information
    ACQUISITION_DISPOSITION = "2.01"
    RESULTS_OF_OPERATIONS = "2.02"
    DIRECT_FINANCIAL_OBLIGATION = "2.03"
    TRIGGERING_EVENTS = "2.04"
    EXIT_DISPOSAL_COSTS = "2.05"
    MATERIAL_IMPAIRMENTS = "2.06"

    # Section 3 – Securities and Trading Markets
    DELISTING_NOTICE = "3.01"
    UNREGISTERED_SALES = "3.02"
    SECURITY_RIGHTS_MODIFICATION = "3.03"

    # Section 4 – Matters Related to Accountants and Financial Statements
    ACCOUNTANT_CHANGE = "4.01"
    NON_RELIANCE = "4.02"

    # Section 5 – Corporate Governance and Management
    CONTROL_CHANGE = "5.01"
    DIRECTOR_OFFICER_CHANGE = "5.02"
    AMENDMENTS_TO_ARTICLES = "5.03"
    TRADING_SUSPENSION = "5.04"
    CODE_OF_ETHICS = "5.05"
    SHELL_COMPANY_STATUS = "5.06"
    SHAREHOLDER_VOTE = "5.07"
    SHAREHOLDER_NOMINATIONS = "5.08"

    # Section 6 – Asset-Backed Securities
    ABS_INFORMATIONAL = "6.01"
    SERVICER_TRUSTEE_CHANGE = "6.02"
    CREDIT_ENHANCEMENT_CHANGE = "6.03"
    DISTRIBUTION_FAILURE = "6.04"
    SECURITIES_ACT_UPDATING = "6.05"
    STATIC_POOL = "6.06"

    # Section 7 – Regulation FD
    REGULATION_FD = "7.01"

    # Section 8 – Other Events
    OTHER_EVENTS = "8.01"

    # Section 9 – Financial Statements and Exhibits
    FINANCIAL_STATEMENTS_EXHIBITS = "9.01"


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


# 8-K items don't have PART divisions
ITEM_8K_TITLES: dict[str, str] = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.04": "Mine Safety – Reporting of Shutdowns and Patterns of Violations",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement of a Registrant",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report or Completed Interim Review",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements of Certain Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year",
    "5.04": "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans",
    "5.05": "Amendments to the Registrant's Code of Ethics, or Waiver of a Provision of the Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Director Nominations",
    "6.01": "ABS Informational and Computational Material",
    "6.02": "Change of Servicer or Trustee",
    "6.03": "Change in Credit Enhancement or Other External Support",
    "6.04": "Failure to Make a Required Distribution",
    "6.05": "Securities Act Updating Disclosure",
    "6.06": "Static Pool",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


class Exhibit(BaseModel):
    """8-K exhibit entry."""
    exhibit_no: str = Field(..., description="Exhibit number (e.g., '99.1', '104')")
    description: str = Field(..., description="Exhibit description")

    model_config = {"frozen": False}


class TextBlock(BaseModel):
    """XBRL TextBlock (e.g., financial statement note)."""

    name: str = Field(..., description="XBRL tag name (e.g., 'us-gaap:DebtDisclosureTextBlock')")
    title: Optional[str] = Field(None, description="Human-readable title (e.g., 'Note 9 – Debt')")
    elements: List['Element'] = Field(default_factory=list, description="Element objects in this TextBlock")

    # Optional: Set by merge_text_blocks() for multi-page notes
    page_start: Optional[int] = Field(None, description="First page this TextBlock appears on")
    page_end: Optional[int] = Field(None, description="Last page this TextBlock appears on")
    source_pages: Optional[List[int]] = Field(None, description="All pages this TextBlock spans")

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @computed_field
    @property
    def element_ids(self) -> List[str]:
        """Get list of element IDs."""
        return [e.id for e in self.elements]

    def __repr__(self) -> str:
        pages_info = f", pages={self.page_start}-{self.page_end}" if self.page_start else ""
        return f"TextBlock(name='{self.name}', title='{self.title}', elements={len(self.elements)}{pages_info})"


class Element(BaseModel):
    """Citable semantic block of content."""

    id: str = Field(..., description="Unique element ID for citation")
    content: str = Field(..., description="Element text content")
    kind: str = Field(..., description="Element type (e.g., 'paragraph', 'table', 'heading')")
    page_start: int = Field(..., description="First page this element appears on")
    page_end: int = Field(..., description="Last page this element appears on")

    model_config = {"frozen": False}

    @computed_field
    @property
    def char_count(self) -> int:
        """Character count of this element."""
        return len(self.content)

    @computed_field
    @property
    def tokens(self) -> int:
        """Token count of this element."""
        return _count_tokens(self.content)

    def __repr__(self) -> str:
        preview = self.content[:80].replace('\n', ' ')
        pages = f"p{self.page_start}" if self.page_start == self.page_end else f"p{self.page_start}-{self.page_end}"
        return f"Element(id='{self.id}', kind='{self.kind}', {pages}, chars={len(self.content)}, preview='{preview}...')"


class Page(BaseModel):
    """Represents a single page of markdown content."""

    number: int = Field(..., description="Page number in the filing")
    content: str = Field(..., description="Markdown content of the page")
    elements: Optional[List[Element]] = Field(None, description="Citable elements on this page")
    text_blocks: Optional[List[TextBlock]] = Field(None, description="XBRL TextBlocks on this page")

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @computed_field
    @property
    def tokens(self) -> int:
        """Total number of tokens on this page."""
        return _count_tokens(self.content)

    def preview(self) -> None:
        """
        Preview the full page content.

        Renders as Markdown in Jupyter/IPython, plain text in console.
        """
        if IPYTHON_AVAILABLE:
            display(IPythonMarkdown(self.content))
        else:
            print(f"=== Page {self.number} ({self.tokens} tokens) ===")
            print(self.content)

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        preview = self.content[:100].replace('\n', ' ')
        elem_info = f", elements={len(self.elements)}" if self.elements else ""
        tb_info = f", text_blocks={len(self.text_blocks)}" if self.text_blocks else ""
        return f"Page(number={self.number}, tokens={self.tokens}{elem_info}{tb_info}, preview='{preview}...')"


class Section(BaseModel):
    """Represents a filing section (e.g., ITEM 1A - Risk Factors)."""

    part: Optional[str] = Field(None, description="Part name (e.g., 'PART I', None for 8-K)")
    item: Optional[str] = Field(None, description="Item identifier (e.g., 'ITEM 1A', 'ITEM 2.02')")
    item_title: Optional[str] = Field(None, description="Item title")
    pages: List[Page] = Field(default_factory=list, description="Pages in this section")
    exhibits: Optional[List[Exhibit]] = Field(None, description="8-K exhibits (Item 9.01 only)")

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @field_validator('pages')
    @classmethod
    def validate_pages_not_empty(cls, v: List[Page]) -> List[Page]:
        """Ensure section has at least one page."""
        if not v:
            raise ValueError("Section must contain at least one page")
        return v

    @computed_field
    @property
    def page_range(self) -> Tuple[int, int]:
        """Get the start and end page numbers for this section."""
        if not self.pages:
            return 0, 0
        return self.pages[0].number, self.pages[-1].number

    @computed_field
    @property
    def tokens(self) -> int:
        """Total number of tokens in this section."""
        return sum(p.tokens for p in self.pages)

    @property
    def content(self) -> str:
        """Get section content with page delimiters."""
        return "\n\n---\n\n".join(p.content for p in self.pages)

    def markdown(self) -> str:
        """Get section content as single markdown string."""
        return "\n\n".join(p.content for p in self.pages)

    def preview(self) -> None:
        """
        Preview the full section content.

        Renders as Markdown in Jupyter/IPython, plain text in console.
        """
        content = self.markdown()

        if IPYTHON_AVAILABLE:
            display(IPythonMarkdown(content))
        else:
            header = f"{self.item}: {self.item_title}"
            print(f"=== {header} ({self.tokens} tokens, pages {self.page_range[0]}-{self.page_range[1]}) ===")
            print(content)

    def __str__(self) -> str:
        return self.markdown()

    def __repr__(self) -> str:
        page_range = self.page_range
        return (
            f"Section(item='{self.item}', title='{self.item_title}', "
            f"pages={page_range[0]}-{page_range[1]}, tokens={self.tokens})"
        )
