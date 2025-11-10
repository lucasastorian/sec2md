import logging
from typing import Union, Tuple, List, Dict, Any

from sec2md.chunker.markdown_chunk import MarkdownChunk
from sec2md.chunker.markdown_blocks import BaseBlock, TextBlock, TableBlock, HeaderBlock

# Rebuild MarkdownChunk after Element is defined
from sec2md.models import Element
MarkdownChunk.model_rebuild()

logger = logging.getLogger(__name__)


class MarkdownChunker:
    """Splits markdown content into chunks"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, pages: List[Any], header: str = None) -> List[MarkdownChunk]:
        """Split the pages into chunks with optional header for embedding context.

        Args:
            pages: List of Page objects
            header: Optional header to prepend to each chunk's embedding_text

        Returns:
            List of MarkdownChunk objects
        """
        # Build element map: page -> List[Element objects]
        page_elements = {}
        for page in pages:
            if hasattr(page, 'elements') and page.elements:
                page_elements[page.number] = page.elements

        blocks = self._split_into_blocks(pages=pages)
        return self._chunk_blocks(blocks=blocks, header=header, page_elements=page_elements)

    def chunk_text(self, text: str) -> List[str]:
        """Chunk a single text string into multiple chunks"""
        from sec2md.models import Page
        pages = [Page(number=0, content=text)]
        chunks = self.split(pages=pages)
        return [chunk.content for chunk in chunks]

    @staticmethod
    def _split_into_blocks(pages: List[Any]):
        """Splits the pages into blocks.

        Args:
            pages: List of Page objects

        Returns:
            List of BaseBlock objects
        """
        from sec2md.models import Page

        blocks = []
        table_content = ""
        last_page = None

        for page in pages:
            last_page = page

            for line in page.content.split('\n'):
                if table_content and not MarkdownChunker._is_table_line(line):
                    blocks.append(TableBlock(content=table_content, page=page.number))
                    table_content = ""

                if line.startswith("#"):
                    blocks.append(HeaderBlock(content=line, page=page.number))

                elif MarkdownChunker._is_table_line(line):
                    table_content += f"{line}\n"

                else:
                    blocks.append(TextBlock(content=line, page=page.number))

        if table_content and last_page:
            blocks.append(TableBlock(content=table_content, page=last_page.number))

        return blocks

    @staticmethod
    def _is_table_line(line: str) -> bool:
        import re
        if '|' not in line:
            return False
        stripped = line.strip()
        if not stripped:
            return False
        align_pattern = re.compile(r'^\s*:?-+:?\s*$')
        cells = [c.strip() for c in stripped.strip('|').split('|')]
        if all(align_pattern.match(c) for c in cells):
            return True
        return True

    def _chunk_blocks(self, blocks: List[BaseBlock], header: str = None, page_elements: dict = None) -> List[MarkdownChunk]:
        """Converts the blocks to chunks"""
        page_elements = page_elements or {}
        chunks = []
        chunk_blocks = []
        num_tokens = 0

        for i, block in enumerate(blocks):
            next_block = blocks[i + 1] if i + 1 < len(blocks) else None

            if block.block_type == 'Text':
                chunk_blocks, num_tokens, chunks = self._process_text_block(
                    block, chunk_blocks, num_tokens, chunks, header, page_elements
                )

            elif block.block_type == 'Table':
                chunk_blocks, num_tokens, chunks = self._process_table_block(
                    block, chunk_blocks, num_tokens, chunks, blocks, i, header, page_elements
                )

            else:
                chunk_blocks, num_tokens, chunks = self._process_header_table_block(
                    block, chunk_blocks, num_tokens, chunks, next_block, header, page_elements
                )

        if chunk_blocks:
            self._finalize_chunk(chunks, chunk_blocks, header, page_elements)

        return chunks

    def _process_text_block(self, block: TextBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                            chunks: List[MarkdownChunk], header: str = None, page_elements: dict = None):
        """Process a text block by breaking it into sentences if needed"""
        sentences = []
        sentences_tokens = 0

        for sentence in block.sentences:
            if num_tokens + sentences_tokens + sentence.tokens > self.chunk_size:
                if sentences:
                    new_block = TextBlock.from_sentences(sentences=sentences, page=block.page)
                    chunk_blocks.append(new_block)
                    num_tokens += sentences_tokens

                chunks, chunk_blocks, num_tokens = self._create_chunk(chunks=chunks, blocks=chunk_blocks, header=header, page_elements=page_elements)

                sentences = [sentence]
                sentences_tokens = sentence.tokens

            else:
                sentences.append(sentence)
                sentences_tokens += sentence.tokens

        if sentences:
            new_block = TextBlock.from_sentences(sentences=sentences, page=block.page)
            chunk_blocks.append(new_block)
            num_tokens += sentences_tokens

        return chunk_blocks, num_tokens, chunks

    def _process_table_block(self, block: BaseBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                             chunks: List[MarkdownChunk], all_blocks: List[BaseBlock], block_idx: int, header: str = None, page_elements: dict = None):
        """Process a table block with optional header backtrack"""
        context = []
        context_tokens = 0

        # Backtrack for header only if 1-2 short blocks precede
        count = 0
        for j in range(block_idx - 1, -1, -1):
            prev = all_blocks[j]
            if prev.page != block.page:
                break
            if prev.block_type == 'Header':
                if context_tokens + prev.tokens <= 128:
                    context.insert(0, prev)
                    context_tokens += prev.tokens
                break
            elif prev.block_type == 'Text' and prev.content.strip():
                count += 1
                if count > 2:
                    break
                if context_tokens + prev.tokens <= 128:
                    context.insert(0, prev)
                    context_tokens += prev.tokens
                else:
                    break

        if num_tokens + context_tokens + block.tokens > self.chunk_size:
            if chunk_blocks:
                chunks, chunk_blocks, num_tokens = self._create_chunk(chunks=chunks, blocks=chunk_blocks, header=header, page_elements=page_elements)

            # If we're backtracking context and the last chunk is ONLY that context, remove it
            if context and chunks and len(chunks[-1].blocks) == len(context):
                if all(chunks[-1].blocks[i] == context[i] for i in range(len(context))):
                    chunks.pop()

            chunk_blocks = context + [block]
            num_tokens = context_tokens + block.tokens
        else:
            chunk_blocks.extend(context + [block])
            num_tokens += context_tokens + block.tokens

        return chunk_blocks, num_tokens, chunks

    def _process_header_table_block(self, block: BaseBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                                    chunks: List[MarkdownChunk], next_block: BaseBlock, header: str = None, page_elements: dict = None):
        """Process a header block"""
        if not chunk_blocks:
            chunk_blocks.append(block)
            num_tokens += block.tokens
            return chunk_blocks, num_tokens, chunks

        # Don't split if current content is small and next is a table
        if next_block and next_block.block_type == 'Table' and num_tokens < self.chunk_overlap:
            chunk_blocks.append(block)
            num_tokens += block.tokens
            return chunk_blocks, num_tokens, chunks

        if num_tokens + block.tokens > self.chunk_size:
            chunks, chunk_blocks, num_tokens = self._create_chunk(chunks=chunks, blocks=chunk_blocks, header=header, page_elements=page_elements)
            chunk_blocks.append(block)
            num_tokens += block.tokens
        else:
            chunk_blocks.append(block)
            num_tokens += block.tokens

        return chunk_blocks, num_tokens, chunks

    def _finalize_chunk(self, chunks: List[MarkdownChunk], blocks: List[BaseBlock], header: str, page_elements: dict):
        """Create chunk with elements from the pages it spans"""
        chunk_pages = set(block.page for block in blocks)
        elements = []
        for page_num in sorted(chunk_pages):
            if page_num in page_elements:
                elements.extend(page_elements[page_num])
        chunks.append(MarkdownChunk(blocks=blocks, header=header, elements=elements))

    def _create_chunk(self, chunks: List[MarkdownChunk], blocks: List[BaseBlock], header: str = None, page_elements: dict = None) -> Tuple[
        List[MarkdownChunk], List[BaseBlock], int]:
        """Creates a chunk and returns overlap blocks"""
        page_elements = page_elements or {}
        self._finalize_chunk(chunks, blocks, header, page_elements)

        if not self.chunk_overlap:
            return chunks, [], 0

        overlap_tokens = 0
        overlap_blocks = []

        for block in reversed(blocks):
            if block.block_type == "Text":
                sentences = []

                for sentence in reversed(block.sentences):

                    if overlap_tokens + sentence.tokens > self.chunk_overlap:
                        text_block = TextBlock.from_sentences(sentences=sentences, page=block.page)
                        overlap_blocks.insert(0, text_block)
                        return chunks, overlap_blocks, overlap_tokens

                    else:
                        sentences.insert(0, sentence)
                        overlap_tokens += sentence.tokens

            else:
                if overlap_tokens + block.tokens > self.chunk_overlap:
                    return chunks, overlap_blocks, overlap_tokens

                else:
                    overlap_blocks.insert(0, block)
                    overlap_tokens += block.tokens

        return chunks, [], 0
