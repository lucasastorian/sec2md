"""sec2md: Convert SEC filings to high-quality Markdown."""

from sec2md.core import convert_to_markdown
from sec2md.utils import flatten_note
from sec2md.sections import extract_sections, get_section
from sec2md.chunking import chunk_pages, chunk_section
from sec2md.models import Page, Section, Item10K, Item10Q, FilingType
from sec2md.chunker.markdown_chunk import MarkdownChunk

__version__ = "0.1.0"
__all__ = [
    "convert_to_markdown",
    "flatten_note",
    "extract_sections",
    "get_section",
    "chunk_pages",
    "chunk_section",
    "Page",
    "Section",
    "Item10K",
    "Item10Q",
    "FilingType",
    "MarkdownChunk",
]
