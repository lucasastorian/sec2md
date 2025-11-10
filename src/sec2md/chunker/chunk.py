from typing import List, Optional, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field, computed_field

from sec2md.chunker.blocks import BaseBlock

if TYPE_CHECKING:
    from sec2md.models import Element
else:
    Element = 'Element'  # Forward reference for Pydantic


class Chunk(BaseModel):
    """Represents a chunk of content that can be embedded"""

    blocks: List[BaseBlock] = Field(..., description="List of markdown blocks in this chunk")
    header: Optional[str] = Field(None, description="Optional header for embedding context")
    elements: List['Element'] = Field(default_factory=list, description="Element objects for citation")
    vector: Optional[List[float]] = Field(None, description="Vector embedding for this chunk")

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @computed_field
    @property
    def page(self) -> int:
        """First page (for backward compatibility)."""
        return self.blocks[0].page if self.blocks else 1

    def set_vector(self, vector: List[float]):
        """Set the vector embedding for this chunk"""
        self.vector = vector

    @computed_field
    @property
    def start_page(self) -> int:
        """First page this chunk appears on (from elements or blocks)."""
        # Prefer elements since they have actual page info from the document
        if self.elements:
            return min(e.page_start for e in self.elements)
        elif self.blocks:
            return min(block.page for block in self.blocks)
        return self.page

    @computed_field
    @property
    def end_page(self) -> int:
        """Last page this chunk appears on (from elements or blocks)."""
        # Prefer elements since they have actual page info from the document
        if self.elements:
            return max(e.page_end for e in self.elements)
        elif self.blocks:
            return max(block.page for block in self.blocks)
        return self.page

    @computed_field
    @property
    def page_range(self) -> Tuple[int, int]:
        """(start_page, end_page) tuple."""
        return (self.start_page, self.end_page)

    @computed_field
    @property
    def content(self) -> str:
        """Get the text content of this chunk"""
        return "\n".join([block.content for block in self.blocks])

    @computed_field
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

    @computed_field
    @property
    def pages(self) -> List[dict]:
        """Returns a list of pages with ONLY this chunk's content (not full page content)"""
        return self.data

    @computed_field
    @property
    def embedding_text(self) -> str:
        """Get the text to use for embedding, with optional header prepended"""
        if self.header:
            return f"{self.header}\n\n...\n\n{self.content}"
        return self.content

    @computed_field
    @property
    def has_table(self) -> bool:
        """Returns True if this chunk contains one or more table blocks"""
        return any(block.block_type == 'Table' for block in self.blocks)

    @computed_field
    @property
    def num_tokens(self) -> int:
        """Returns the total number of tokens in this chunk"""
        return sum(block.tokens for block in self.blocks)

    @computed_field
    @property
    def element_ids(self) -> List[str]:
        """List of element IDs for citations."""
        return [e.id for e in self.elements] if self.elements else []

    def to_dict(self) -> dict:
        """Alias for model_dump() - kept for backward compat during alpha."""
        return self.model_dump()

    def __repr__(self):
        pages_str = f"{self.start_page}-{self.end_page}" if self.start_page != self.end_page else str(self.start_page)
        return f"Chunk(pages={pages_str}, blocks={len(self.blocks)}, tokens={self.num_tokens})"

    def _repr_markdown_(self):
        """This method is called by IPython to display as Markdown"""
        return self.content
