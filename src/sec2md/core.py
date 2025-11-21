"""Core conversion functionality."""

from typing import overload, List, Literal
from sec2md.utils import is_url, fetch
from sec2md.parser import Parser
from sec2md.models import Page


@overload
def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = False,
) -> str: ...


@overload
def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = True,
) -> List[Page]: ...


def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = False,
) -> str | List[Page]:
    """
    Convert SEC filing HTML to Markdown.

    Args:
        source: URL or HTML string/bytes
        user_agent: User agent for EDGAR requests (required for sec.gov URLs)
        return_pages: If True, returns List[Page] instead of markdown string

    Returns:
        Markdown string (default) or List[Page] if return_pages=True

    Raises:
        ValueError: If source appears to be PDF content or other non-HTML format

    Examples:
        >>> # From URL - get markdown
        >>> md = convert_to_markdown(
        ...     "https://www.sec.gov/Archives/edgar/data/.../10k.htm",
        ...     user_agent="Lucas Astorian <lucas@intellifin.ai>"
        ... )

        >>> # Get pages for section extraction
        >>> pages = convert_to_markdown(filing.html(), return_pages=True)

        >>> # With edgartools
        >>> from edgar import Company, set_identity
        >>> set_identity("Lucas Astorian <lucas@intellifin.ai>")
        >>> company = Company('AAPL')
        >>> filing = company.get_filings(form="10-K").latest()
        >>> md = convert_to_markdown(filing.html())
    """
    # Handle bytes input
    if isinstance(source, bytes):
        # Check if it's PDF
        if source.startswith(b'%PDF'):
            raise ValueError(
                "PDF content detected. This library only supports HTML input. "
                "Please extract HTML from the filing first."
            )
        source = source.decode('utf-8', errors='ignore')

    # Check for PDF in string
    if isinstance(source, str) and source.strip().startswith('%PDF'):
        raise ValueError(
            "PDF content detected. This library only supports HTML input. "
            "Please extract HTML from the filing first."
        )

    # Fetch from URL if needed
    if is_url(source):
        html = fetch(source, user_agent=user_agent)
    else:
        html = source

    # Parse and convert
    parser = Parser(html)

    if return_pages:
        return parser.get_pages()
    else:
        return parser.markdown()


def parse_filing(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    include_elements: bool = True,
) -> List[Page]:
    """
    Parse SEC filing HTML into structured Page objects.

    Convenience wrapper around Parser that returns Page objects with optional
    Element extraction for citations and chunking.

    Args:
        source: URL or HTML string/bytes
        user_agent: User agent for EDGAR requests (required for sec.gov URLs)
        include_elements: If True, extract citable elements (default: True)

    Returns:
        List[Page]: Parsed pages with content, elements, and text blocks

    Raises:
        ValueError: If source appears to be PDF content or other non-HTML format

    Examples:
        >>> # Parse from URL
        >>> pages = parse_filing(
        ...     "https://www.sec.gov/Archives/edgar/data/.../10k.htm",
        ...     user_agent="Your Name <email@domain.com>"
        ... )

        >>> # Parse without elements (faster)
        >>> pages = parse_filing(html_content, include_elements=False)

        >>> # Access page data
        >>> page = pages[0]
        >>> print(page.number, page.content, page.elements)

        >>> # Convert to dict
        >>> page_dict = page.model_dump()  # Full serialization
        >>> essentials = page.model_dump(include={'number', 'content', 'elements'})
    """
    # Handle bytes input
    if isinstance(source, bytes):
        # Check if it's PDF
        if source.startswith(b'%PDF'):
            raise ValueError(
                "PDF content detected. This library only supports HTML input. "
                "Please extract HTML from the filing first."
            )
        source = source.decode('utf-8', errors='ignore')

    # Check for PDF in string
    if isinstance(source, str) and source.strip().startswith('%PDF'):
        raise ValueError(
            "PDF content detected. This library only supports HTML input. "
            "Please extract HTML from the filing first."
        )

    # Fetch from URL if needed
    if is_url(source):
        html = fetch(source, user_agent=user_agent)
    else:
        html = source

    # Parse and return pages
    parser = Parser(html)
    return parser.get_pages(include_elements=include_elements)
