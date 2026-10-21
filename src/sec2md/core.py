"""Core conversion functionality."""

import base64
import logging
import re
from typing import List, Literal, overload
from urllib.parse import urljoin

from sec2md.models import Page
from sec2md.parser import Parser
from sec2md.utils import fetch, is_url

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
    """Fetch the images the HTML references (relative to source_url) and inline them as base64
    data URIs; an image that cannot be fetched keeps its URL."""
    import requests

    base_url = source_url.rsplit('/', 1)[0] + '/'
    headers = {"User-Agent": user_agent} if user_agent else {}

    def _replace_src(match: re.Match) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)  # '<img ... src="', URL, quote
        if src.startswith('data:'):
            return match.group(0)
        abs_url = urljoin(base_url, src)
        try:
            resp = requests.get(abs_url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch image: %s", abs_url)
            return match.group(0)
        ext = '.' + src.rsplit('.', 1)[-1].lower() if '.' in src else ''
        encoded = base64.b64encode(resp.content).decode('ascii')
        return f"{prefix}data:{_MIME_TYPES.get(ext, 'image/png')};base64,{encoded}{suffix}"

    return re.sub(r'(<img[^>]+src=["\'])([^"\']+)(["\'])', _replace_src, html, flags=re.IGNORECASE)


def _parser(source: str | bytes, user_agent: str | None, embed_images: bool) -> Parser:
    """A Parser over HTML given as a string, bytes or a URL (fetched)."""
    url = source if isinstance(source, str) and is_url(source) else None
    if isinstance(source, bytes):
        source = source.decode('utf-8', errors='ignore')
    if source.lstrip().startswith('%PDF'):
        raise ValueError(
            "PDF content detected. This library only supports HTML input. "
            "Please extract HTML from the filing first."
        )
    html = fetch(source, user_agent=user_agent) if is_url(source) else source
    if embed_images and url:
        html = _embed_images(html, url, user_agent)
    return Parser(html)


@overload
def convert_to_markdown(source: str | bytes, *, user_agent: str | None = None,
                        return_pages: Literal[False] = False, embed_images: bool = False) -> str: ...


@overload
def convert_to_markdown(source: str | bytes, *, user_agent: str | None = None,
                        return_pages: Literal[True], embed_images: bool = False) -> List[Page]: ...


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
        ...     user_agent="Lucas Astorian <lucasastorian@gmail.com>"
        ... )

        >>> # Get pages for section extraction
        >>> pages = convert_to_markdown(filing.html(), return_pages=True)

        >>> # With edgartools
        >>> from edgar import Company, set_identity
        >>> set_identity("Lucas Astorian <lucasastorian@gmail.com>")
        >>> company = Company('AAPL')
        >>> filing = company.get_filings(form="10-K").latest()
        >>> md = convert_to_markdown(filing.html())
    """
    parser = _parser(source, user_agent, embed_images)
    if return_pages:
        return parser.get_pages()
    # Just the text: no citable elements to build
    return "\n\n".join(page.content for page in parser.get_pages(include_elements=False) if page.content)


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
    return _parser(source, user_agent, embed_images).get_pages(include_elements=include_elements)
