"""Chunking utilities for page-aware splitting."""

from typing import List, Optional
from collections import defaultdict
from sec2md.models import Page, Section, TextBlock
from sec2md.chunker.chunker import Chunker
from sec2md.chunker.chunk import Chunk


def chunk_pages(
    pages: List[Page],
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[Chunk]:
    """
    Chunk pages into overlapping chunks.

    Args:
        pages: List of Page objects (with optional elements)
        chunk_size: Target chunk size in tokens (estimated as chars/4)
        chunk_overlap: Overlap between chunks in tokens
        header: Optional header to prepend to each chunk's embedding_text

    Returns:
        List of Chunk objects with page tracking and elements

    Example:
        >>> pages = sec2md.convert_to_markdown(html, return_pages=True, include_elements=True)
        >>> chunks = sec2md.chunk_pages(pages, chunk_size=512)
        >>> for chunk in chunks:
        ...     print(f"Page {chunk.page}: {chunk.content[:100]}...")
        ...     print(f"Elements: {chunk.elements}")
    """
    chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.split(pages=pages, header=header)


def chunk_section(
    section: Section,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[Chunk]:
    """
    Chunk a filing section into overlapping chunks.

    Args:
        section: Section object from extract_sections()
        chunk_size: Target chunk size in tokens (estimated as chars/4)
        chunk_overlap: Overlap between chunks in tokens
        header: Optional header to prepend to each chunk's embedding_text

    Returns:
        List of Chunk objects

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


def merge_text_blocks(pages: List[Page]) -> List[TextBlock]:
    """
    Merge multi-page TextBlocks into single TextBlock objects.

    When a financial note (e.g., Debt Disclosure) spans multiple pages,
    this merges all elements and page references into one TextBlock.

    Args:
        pages: List of Page objects with text_blocks populated

    Returns:
        List of merged TextBlock objects with page metadata:
        - page_start: First page the note appears on
        - page_end: Last page the note appears on
        - source_pages: All pages the note spans
        - elements: All elements from all pages

    Example:
        >>> pages = parser.get_pages(include_elements=True)
        >>> merged = merge_text_blocks(pages)
        >>> for tb in merged:
        ...     print(f"{tb.title}: pages {tb.page_start}-{tb.page_end}")
        Debt Disclosure: pages 45-46
        Segment Reporting: pages 49-50
    """
    # Group by TextBlock name
    tb_map = defaultdict(lambda: {
        "name": None,
        "title": None,
        "elements": [],
        "page_start": float('inf'),
        "page_end": -1,
        "pages": set()
    })

    for page in pages:
        if page.text_blocks:
            for tb in page.text_blocks:
                tb_map[tb.name]["name"] = tb.name
                tb_map[tb.name]["title"] = tb.title
                tb_map[tb.name]["elements"].extend(tb.elements)
                tb_map[tb.name]["page_start"] = min(tb_map[tb.name]["page_start"], page.number)
                tb_map[tb.name]["page_end"] = max(tb_map[tb.name]["page_end"], page.number)
                tb_map[tb.name]["pages"].add(page.number)

    # Create merged TextBlock objects
    merged = []
    for tb_data in tb_map.values():
        tb = TextBlock(
            name=tb_data["name"],
            title=tb_data["title"],
            elements=tb_data["elements"],
            page_start=tb_data["page_start"],
            page_end=tb_data["page_end"],
            source_pages=sorted(tb_data["pages"])
        )
        merged.append(tb)

    return merged


def chunk_text_block(
    text_block: TextBlock,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[Chunk]:
    """
    Chunk a single TextBlock (financial note).

    Args:
        text_block: TextBlock object (possibly spanning multiple pages)
        chunk_size: Target chunk size in tokens (estimated as chars/4)
        chunk_overlap: Overlap between chunks in tokens
        header: Optional header to prepend to each chunk's embedding_text

    Returns:
        List of Chunk objects with elements preserved

    Example:
        >>> merged = merge_text_blocks(pages)
        >>> debt_note = [tb for tb in merged if "Debt" in tb.title][0]
        >>> chunks = chunk_text_block(debt_note, chunk_size=512, header="Company: AAPL | Note: Debt")
        >>> print(f"Chunked {debt_note.title} into {len(chunks)} chunks")
        >>> print(f"Note spans pages {debt_note.page_start}-{debt_note.page_end}")
    """
    # Group elements by page
    elements_by_page = defaultdict(list)
    for elem in text_block.elements:
        # Use page_start for grouping (elements are always on single pages in practice)
        elements_by_page[elem.page_start].append(elem)

    # Create one Page per page the TextBlock spans, with only elements from that page
    pages = []
    for page_num in sorted(elements_by_page.keys()):
        elems = elements_by_page[page_num]
        # Join content from elements on this page
        content = "\n\n".join(e.content for e in elems)

        pages.append(Page(
            number=page_num,     # Real page number
            content=content,     # Only content from this page
            elements=elems       # Only elements from this page
        ))

    chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    return chunker.split(pages=pages, header=header)
