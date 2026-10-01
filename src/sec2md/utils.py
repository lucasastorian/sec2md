"""Utility functions."""

import functools
import re
from typing import Collection, Iterator, List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag

_ws = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    return _ws.sub(" ", text).strip()


_CSS_LENGTH = {prop: re.compile(rf"(?<![\w-]){prop}:\s*(\d+(?:\.\d+)?)(px|pt)") for prop in ("top", "left", "bottom")}


def css_px(style: str, prop: str) -> Optional[float]:
    """An inline style's top, left or bottom in px, pt converted (margin-top is not top)."""
    m = _CSS_LENGTH[prop].search(style)
    if m is None:
        return None
    return float(m.group(1)) * (4.0 / 3.0) if m.group(2) == "pt" else float(m.group(1))


def iter_tags(node: Tag, names: Collection[str]) -> Iterator[Tag]:
    """Descendant tags named one of `names`, in document order: find_all(names) without
    bs4's per-tag filter machinery, which costs more than the walk itself."""
    for d in node.descendants:
        if isinstance(d, Tag) and d.name in names:
            yield d


@functools.lru_cache(maxsize=None)
def _encoding():
    """tiktoken's cl100k_base, or None: not installed, or its BPE file cannot be fetched (offline)."""
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


@functools.lru_cache(maxsize=8192)
def count_tokens(text: str) -> int:
    """Tokens in text: tiktoken cl100k_base when available, else chars/4 (at least 1).
    Cached: chunking counts the same sentences and blocks several times."""
    encoding = _encoding()
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:  # e.g. a disallowed special token in the text
            pass
    return max(1, len(text) // 4)


NUMERIC_RE = re.compile(r"""
    ^\s*
    [\(\[]?                      # optional opening paren/bracket
    [\-—–]?\s*                   # optional dash
    [$€£¥]?\s*                   # optional currency
    \d+(?:[.,]\d{3})*           # integer part (with thousands)
    (?:[.,]\d+)?                # decimals
    \s*%?                       # optional percent
    [\)\]]?\s*$                 # optional closing paren/bracket
""", re.X)


def median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
    return sorted_vals[n // 2]


def is_url(source: str) -> bool:
    """
    Check if source is a valid URL using urllib.parse.

    Args:
        source: String to check

    Returns:
        True if source is a valid URL with http/https scheme
    """
    try:
        result = urlparse(source)
        return all([result.scheme, result.netloc]) and result.scheme in ('http', 'https')
    except Exception:
        return False


def is_edgar_url(url: str) -> bool:
    """Check if URL is an SEC EDGAR URL."""
    return "sec.gov" in url.lower()


def fetch(url: str, user_agent: str | None = None) -> str:
    """
    Fetch HTML content from a URL.

    Args:
        url: The URL to fetch
        user_agent: User agent string (required for EDGAR URLs)

    Returns:
        HTML content as string

    Raises:
        ValueError: If EDGAR URL is accessed without user_agent
        requests.RequestException: If request fails
    """
    if is_edgar_url(url) and not user_agent:
        raise ValueError(
            "SEC EDGAR requires a User-Agent header. "
            "Pass user_agent='YourName your@email.com'"
        )

    import requests

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def flatten_note(content: str) -> Optional[str]:
    """
    Flatten note structure by removing the outer table wrapper.

    Notes to financial statements are often wrapped in an unnecessary outer table
    with a single cell containing the actual content. This function unwraps that
    outer table to reveal the properly structured content inside.

    Args:
        content: HTML string containing the note content

    Returns:
        Flattened HTML string, or None if flattening fails

    Example:
        >>> from edgar import Company, set_identity
        >>> import sec2md
        >>>
        >>> set_identity("Your Name <you@example.com>")
        >>> company = Company('AAPL')
        >>> filing = company.get_filings(form="10-K").latest()
        >>> notes = filing.reports.get_by_category("Notes")
        >>> note = notes.get_by_short_name("Revenue")
        >>>
        >>> # Flatten the note wrapper
        >>> flattened_html = sec2md.flatten_note(note.content)
        >>> md = sec2md.convert_to_markdown(flattened_html)
    """
    soup = BeautifulSoup(content, 'lxml')
    elements = []

    body = soup.find("body")
    if not body:
        return None

    table = body.find("table")
    if table is None:
        return None

    for row in table.find_all('tr', recursive=False):
        cells = row.find_all(['th', 'td'], recursive=False)

        for cell in cells:
            elements.append(cell)

    if len(elements) == 0:
        return None

    return ''.join([str(element) for element in elements])
