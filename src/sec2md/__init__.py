"""sec2md: Convert SEC filings to high-quality Markdown."""

from sec2md.core import convert_to_markdown
from sec2md.utils import flatten_note
from sec2md.sections import extract_sections, get_section
from sec2md.chunking import chunk_pages, chunk_section, merge_text_blocks, chunk_text_block
from sec2md.models import Page, Section, Item10K, Item10Q, Item8K, FilingType, Element, TextBlock, Exhibit
from sec2md.chunker.chunk import Chunk
from sec2md.chunker.chunker import Chunker
from sec2md.parser import Parser
from sec2md.section_extractor import SectionExtractor

__version__ = "0.1.5"
__all__ = [
    "convert_to_markdown",
    "flatten_note",
    "extract_sections",
    "get_section",
    "chunk_pages",
    "chunk_section",
    "merge_text_blocks",
    "chunk_text_block",
    "Page",
    "Section",
    "Element",
    "TextBlock",
    "Exhibit",
    "Item10K",
    "Item10Q",
    "Item8K",
    "FilingType",
    "Chunk",
    "Chunker",
    "Parser",
    "SectionExtractor",
]
