from typing import List, Optional

from sec2md.chunker.markdown_blocks import BaseBlock


class MarkdownChunk:
    """Represents a chunk of markdown content that can be embedded"""

    def __init__(self, blocks: List[BaseBlock], header: Optional[str] = None):
        """Initialize a markdown chunk with blocks and optional header for embedding"""
        self.vector: Optional[List[float]] = None
        self.blocks = blocks
        self.page = blocks[0].page
        self.header = header

    def set_vector(self, vector: List[float]):
        """Set the vector embedding for this chunk"""
        self.vector = vector

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

    def __repr__(self):
        return f"MarkdownChunk(page={self.page}, blocks={len(self.blocks)})"

    def _repr_markdown_(self):
        """This method is called by IPython to display as Markdown"""
        return self.content
