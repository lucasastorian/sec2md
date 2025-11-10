from typing import List, Optional, TYPE_CHECKING

from sec2md.chunker.markdown_blocks import BaseBlock

if TYPE_CHECKING:
    from sec2md.models import Element


class MarkdownChunk:
    """Represents a chunk of markdown content that can be embedded"""

    def __init__(self, blocks: List[BaseBlock], header: Optional[str] = None,
                 elements: Optional[List['Element']] = None):
        """Initialize a markdown chunk with blocks and optional header for embedding

        Args:
            blocks: List of markdown blocks in this chunk
            header: Optional header for embedding context
            elements: List of Element objects this chunk overlaps with (for citation)
        """
        self.vector: Optional[List[float]] = None
        self.blocks = blocks
        self.page = blocks[0].page  # Kept for backward compatibility
        self.header = header
        self.elements = elements or []

    def set_vector(self, vector: List[float]):
        """Set the vector embedding for this chunk"""
        self.vector = vector

    @property
    def start_page(self) -> int:
        """First page this chunk appears on (from elements or blocks)."""
        # Prefer elements since they have actual page info from the document
        if self.elements:
            return min(e.page_start for e in self.elements)
        elif self.blocks:
            return min(block.page for block in self.blocks)
        return self.page

    @property
    def end_page(self) -> int:
        """Last page this chunk appears on (from elements or blocks)."""
        # Prefer elements since they have actual page info from the document
        if self.elements:
            return max(e.page_end for e in self.elements)
        elif self.blocks:
            return max(block.page for block in self.blocks)
        return self.page

    @property
    def page_range(self) -> tuple:
        """(start_page, end_page) tuple."""
        return (self.start_page, self.end_page)

    @property
    def content(self) -> str:
        """Get the text content of this chunk"""
        return "\n".join([block.content for block in self.blocks])

    @property
    def data(self) -> List[dict]:
        """Returns a list of block data grouped by page with ONLY the chunk's content"""
        page_blocks = {}

        for block in self.blocks:
            if block.page not in page_blocks:
                page_blocks[block.page] = []
            page_blocks[block.page].append(block)

        page_content_data = []
        for page, blocks in page_blocks.items():
            # Only include the content from blocks in THIS chunk, not full page content
            page_content = "\n".join(block.content for block in blocks)
            if not page_content.strip():
                continue

            page_content_data.append({
                "page": page,
                "content": page_content
            })

        return sorted(page_content_data, key=lambda x: x["page"])

    @property
    def pages(self) -> List[dict]:
        """Returns a list of pages with ONLY this chunk's content (not full page content)"""
        return self.data

    @property
    def embedding_text(self) -> str:
        """Get the text to use for embedding, with optional header prepended"""
        if self.header:
            return f"{self.header}\n\n...\n\n{self.content}"
        return self.content

    @property
    def has_table(self) -> bool:
        """Returns True if this chunk contains one or more table blocks"""
        return any(block.block_type == 'Table' for block in self.blocks)

    @property
    def num_tokens(self) -> int:
        """Returns the total number of tokens in this chunk"""
        return sum(block.tokens for block in self.blocks)

    def to_dict(self) -> dict:
        """Convert chunk to dictionary representation.

        Returns:
            Dictionary with chunk metadata and content:
            - content: The markdown content
            - start_page: First page number
            - end_page: Last page number
            - num_tokens: Token count
            - has_table: Whether chunk contains tables
            - element_ids: List of element IDs (for citations)
            - header: Optional embedding header
        """
        return {
            "content": self.content,
            "embedding_text": self.embedding_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "num_tokens": self.num_tokens,
            "has_table": self.has_table,
            "element_ids": [e.id for e in self.elements] if self.elements else [],
            "header": self.header,
        }

    def dict(self) -> dict:
        """Alias for to_dict() for Pydantic-style API."""
        return self.to_dict()

    def __repr__(self):
        pages_str = f"{self.start_page}-{self.end_page}" if self.start_page != self.end_page else str(self.start_page)
        return f"MarkdownChunk(pages={pages_str}, blocks={len(self.blocks)}, tokens={self.num_tokens})"

    def _repr_markdown_(self):
        """This method is called by IPython to display as Markdown"""
        return self.content
