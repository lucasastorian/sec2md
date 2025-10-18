"""Chunking utilities for page-aware markdown splitting."""

from typing import List, Optional
from sec2md.models import Page, Section
from sec2md.chunker.markdown_chunker import MarkdownChunker
from sec2md.chunker.markdown_chunk import MarkdownChunk


def chunk_pages(
    pages: List[Page],
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[MarkdownChunk]:
    """
    Chunk pages into overlapping markdown chunks.

    Args:
        pages: List of Page objects
        chunk_size: Target chunk size in tokens (estimated as chars/4)
        chunk_overlap: Overlap between chunks in tokens
        header: Optional header to prepend to each chunk's embedding_text

    Returns:
        List of MarkdownChunk objects with page tracking

    Example:
        >>> pages = sec2md.convert_to_markdown(html, return_pages=True)
        >>> chunks = sec2md.chunk_pages(pages, chunk_size=512)
        >>> for chunk in chunks:
        ...     print(f"Page {chunk.page}: {chunk.content[:100]}...")
    """
    chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    pages_data = [{"page": p.number, "content": p.content} for p in pages]
    return chunker.split(pages=pages_data, header=header)


def chunk_section(
    section: Section,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[MarkdownChunk]:
    """
    Chunk a filing section into overlapping markdown chunks.

    Args:
        section: Section object from extract_sections()
        chunk_size: Target chunk size in tokens (estimated as chars/4)
        chunk_overlap: Overlap between chunks in tokens
        header: Optional header to prepend to each chunk's embedding_text

    Returns:
        List of MarkdownChunk objects

    Example:
        >>> sections = sec2md.extract_sections(pages, filing_type="10-K")
        >>> risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
        >>> chunks = sec2md.chunk_section(risk, chunk_size=512)
    """
    return chunk_pages(
        pages=section.pages,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        header=header
    )
