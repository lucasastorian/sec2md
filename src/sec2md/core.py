"""Core conversion functionality."""

import re
import base64
import logging
from typing import overload, List, Literal
from urllib.parse import urljoin

import requests

from sec2md.utils import is_url, fetch
from sec2md.parser import Parser
from sec2md.models import Page

logger = logging.getLogger(__name__)

_MIME_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.ico': 'image/x-icon',
}


def _embed_images(html: str, source_url: str, user_agent: str | None = None) -> str:
    """Fetch images referenced in HTML and embed them as base64 data URIs.

    Args:
        html: HTML string with <img> tags containing relative or absolute URLs.
        source_url: The URL the HTML was fetched from, used to resolve relative paths.
        user_agent: Optional user agent for image requests.

    Returns:
        HTML with image src attributes replaced by data URIs where possible.
    """
    base_url = source_url.rsplit('/', 1)[0] + '/'

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    def _replace_src(match: re.Match) -> str:
        prefix = match.group(1)   # '<img ... src="'
        src = match.group(2)      # the URL
        suffix = match.group(3)   # closing quote

        # Skip already-embedded data URIs
        if src.startswith('data:'):
            return match.group(0)

        abs_url = urljoin(base_url, src)

        try:
            resp = requests.get(abs_url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch image: %s", abs_url)
            return match.group(0)

        # Detect MIME type from extension
        ext = '.' + src.rsplit('.', 1)[-1].lower() if '.' in src else ''
        mime = _MIME_TYPES.get(ext, 'image/png')

        encoded = base64.b64encode(resp.content).decode('ascii')
        return f"{prefix}data:{mime};base64,{encoded}{suffix}"

    return re.sub(
        r'(<img[^>]+src=["\'])([^"\']+)(["\'])',
        _replace_src,
        html,
        flags=re.IGNORECASE,
    )


def _resolve_source(source: str | bytes, user_agent: str | None = None) -> str:
    """Validate input and resolve to HTML string."""
    if isinstance(source, bytes):
        if source.startswith(b'%PDF'):
            raise ValueError(
                "PDF content detected. This library only supports HTML input. "
                "Please extract HTML from the filing first."
            )
        source = source.decode('utf-8', errors='ignore')

    if isinstance(source, str) and source.strip().startswith('%PDF'):
        raise ValueError(
            "PDF content detected. This library only supports HTML input. "
            "Please extract HTML from the filing first."
        )

    if is_url(source):
        return fetch(source, user_agent=user_agent)
    return source


@overload
def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = False,
    embed_images: bool = False,
) -> str: ...


@overload
def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = True,
    embed_images: bool = False,
) -> List[Page]: ...


def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = False,
    embed_images: bool = False,
) -> str | List[Page]:
    """
    Convert SEC filing HTML to Markdown.

    Args:
        source: URL or HTML string/bytes
        user_agent: User agent for EDGAR requests (required for sec.gov URLs)
        return_pages: If True, returns List[Page] instead of markdown string
        embed_images: If True, fetch and embed images as base64 data URIs (default: False)

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
    source_url = source if isinstance(source, str) and is_url(source) else None
    html = _resolve_source(source, user_agent=user_agent)

    if embed_images and source_url:
        html = _embed_images(html, source_url, user_agent)

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
    embed_images: bool = False,
) -> List[Page]:
    """
    Parse SEC filing HTML into structured Page objects.

    Convenience wrapper around Parser that returns Page objects with optional
    Element extraction for citations and chunking.

    Args:
        source: URL or HTML string/bytes
        user_agent: User agent for EDGAR requests (required for sec.gov URLs)
        include_elements: If True, extract citable elements (default: True)
        embed_images: If True, fetch and embed images as base64 data URIs (default: False)

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
    source_url = source if isinstance(source, str) and is_url(source) else None
    html = _resolve_source(source, user_agent=user_agent)

    if embed_images and source_url:
        html = _embed_images(html, source_url, user_agent)

    parser = Parser(html)
    return parser.get_pages(include_elements=include_elements)
