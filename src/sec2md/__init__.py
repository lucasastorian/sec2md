"""sec2md: Convert SEC filings to high-quality Markdown."""

from sec2md.core import convert_to_markdown
from sec2md.utils import flatten_note
from sec2md.sections import extract_sections, get_section
from sec2md.chunking import chunk_pages, chunk_section
from sec2md.models import Page, Section, Item10K, Item10Q, FilingType, Element, TextBlock
from sec2md.chunker.markdown_chunk import MarkdownChunk
from sec2md.chunker.markdown_chunker import MarkdownChunker
from sec2md.parser import Parser
from sec2md.section_extractor import SectionExtractor

__version__ = "0.1.3"
__all__ = [
    "convert_to_markdown",
    "flatten_note",
    "extract_sections",
    "get_section",
    "chunk_pages",
    "chunk_section",
    "Page",
    "Section",
    "Element",
    "TextBlock",
    "Item10K",
    "Item10Q",
    "FilingType",
    "MarkdownChunk",
    "MarkdownChunker",
    "Parser",
    "SectionExtractor",
]
