import logging
import re
from typing import Union, Tuple, List, Dict, Any, Optional

from sec2md.chunker.chunk import Chunk
from sec2md.chunker.blocks import BaseBlock, TextBlock, TableBlock, HeaderBlock, estimate_tokens

# Rebuild Chunk after Element is defined
from sec2md.models import Element
Chunk.model_rebuild()

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass  # Element already imported above

logger = logging.getLogger(__name__)


class Chunker:
    """Splits content into chunks"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128, max_table_tokens: int = 2048):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_table_tokens = max_table_tokens

    def split(self, pages: List[Any], header: str = None) -> List[Chunk]:
        """Split the pages into chunks with optional header for embedding context.

        Args:
            pages: List of Page objects
            header: Optional header to prepend to each chunk's embedding_text

        Returns:
            List of Chunk objects
        """
        # Build element map: page -> List[Element objects]
        page_elements = {}
        element_by_id = {}
        for page in pages:
            if hasattr(page, 'elements') and page.elements:
                page_elements[page.number] = page.elements
                for elem in page.elements:
                    element_by_id[elem.id] = elem

        # Build page content map: page number -> content (fallback locating)
        page_contents = {}
        for page in pages:
            if hasattr(page, 'content') and page.content:
                page_contents[page.number] = page.content

        # Build display_page map: page number -> display_page
        display_page_map = {}
        for page in pages:
            if hasattr(page, 'display_page') and page.display_page is not None:
                display_page_map[page.number] = page.display_page

        use_elements = any(page_elements.values())
        blocks, synthetic_elements = self._split_into_blocks(pages=pages, use_elements=use_elements)

        # Merge synthetic elements (from table splitting) into element_by_id
        element_by_id.update(synthetic_elements)

        return self._chunk_blocks(
            blocks=blocks,
            header=header,
            page_elements=page_elements,
            display_page_map=display_page_map,
            page_contents=page_contents,
            element_by_id=element_by_id
        )

    def chunk_text(self, text: str) -> List[str]:
        """Chunk a single text string into multiple chunks"""
        from sec2md.models import Page
        pages = [Page(number=0, content=text)]
        chunks = self.split(pages=pages)
        return [chunk.content for chunk in chunks]

    def _split_into_blocks(self, pages: List[Any], use_elements: bool = False) -> Tuple[List[BaseBlock], Dict[str, Element]]:
        """Splits the pages into blocks.

        Returns:
            Tuple of (blocks, synthetic_elements) where synthetic_elements contains
            any new elements created from splitting large tables.
        """
        if use_elements:
            return self._split_from_elements(pages)
        else:
            # Text-based splitting doesn't produce synthetic elements
            return self._split_from_text(pages), {}

    def _split_table_element(self, elem: Element, page_number: int) -> List[Tuple[Element, TableBlock]]:
        """Split an oversized table element into smaller synthetic elements with corresponding blocks.

        Returns:
            List of (Element, TableBlock) tuples. Each element has sliced content matching its block.
        """
        content = elem.content
        tokens = estimate_tokens(content)

        # No splitting needed
        if not self.max_table_tokens or tokens <= self.max_table_tokens:
            block = TableBlock(content=content, page=page_number, element_ids=[elem.id])
            return [(elem, block)]

        lines = [line for line in content.split('\n') if line.strip()]
        if len(lines) <= 2:
            # Table too small to split (just header + separator)
            block = TableBlock(content=content, page=page_number, element_ids=[elem.id])
            return [(elem, block)]

        header_line = lines[0]
        separator_line = lines[1] if len(lines) > 1 else ""
        data_rows = lines[2:]

        # Build ellipsis row matching column count
        header_cells = [cell.strip() for cell in header_line.strip().split('|') if cell.strip()]
        num_cols = max(1, len(header_cells))
        ellipsis_row = "|" + "|".join(["..."] * num_cols) + "|"
        if not separator_line:
            separator_line = "|" + "|".join(["---"] * num_cols) + "|"

        results: List[Tuple[Element, TableBlock]] = []
        row_idx = 0
        part_idx = 0

        while row_idx < len(data_rows):
            base_lines = [header_line, separator_line]
            if row_idx > 0:
                base_lines.append(ellipsis_row)

            segment_rows = []
            while row_idx < len(data_rows):
                next_row = data_rows[row_idx]
                candidate_lines = base_lines + segment_rows + [next_row]
                if row_idx < len(data_rows) - 1:
                    candidate_lines.append(ellipsis_row)
                candidate_tokens = estimate_tokens("\n".join(candidate_lines))

                # Over budget and we have rows - stop here
                if candidate_tokens > self.max_table_tokens and segment_rows:
                    break

                # Over budget but no rows yet - take this one anyway (single row exceeds limit)
                if candidate_tokens > self.max_table_tokens:
                    segment_rows.append(next_row)
                    row_idx += 1
                    break

                segment_rows.append(next_row)
                row_idx += 1

            content_lines = base_lines + segment_rows
            if row_idx < len(data_rows):
                content_lines.append(ellipsis_row)

            segment_content = "\n".join(content_lines)
            segment_id = f"{elem.id}:part-{part_idx}"

            # Create synthetic element with sliced content
            segment_element = Element(
                id=segment_id,
                content=segment_content,
                kind=elem.kind,
                page_start=elem.page_start,
                page_end=elem.page_end,
                content_start_offset=elem.content_start_offset,
                content_end_offset=elem.content_end_offset
            )

            segment_block = TableBlock(
                content=segment_content,
                page=page_number,
                element_ids=[segment_id]
            )

            results.append((segment_element, segment_block))
            part_idx += 1

        return results

    def _split_from_elements(self, pages: List[Any]) -> Tuple[List[BaseBlock], Dict[str, Element]]:
        """Build blocks directly from parser elements.

        Returns:
            Tuple of (blocks, synthetic_elements) where synthetic_elements contains
            any new elements created from splitting large tables.
        """
        blocks: List[BaseBlock] = []
        synthetic_elements: Dict[str, Element] = {}

        for page in pages:
            elems = getattr(page, 'elements', None)
            if not elems:
                blocks.extend(self._split_from_text([page]))
                continue

            # Stable order: by offset when available, else original index
            ordered = sorted(
                enumerate(elems),
                key=lambda pair: (
                    pair[1].content_start_offset if pair[1].content_start_offset is not None else float('inf'),
                    pair[0]
                )
            )

            for _, elem in ordered:
                kind = (elem.kind or "").lower()
                if kind == "table":
                    # Split large tables into multiple elements + blocks
                    for split_elem, split_block in self._split_table_element(elem, page.number):
                        if split_elem.id != elem.id:
                            # This is a synthetic element from splitting
                            synthetic_elements[split_elem.id] = split_elem
                        blocks.append(split_block)
                elif kind == "header":
                    blocks.append(HeaderBlock(content=elem.content, page=page.number, element_ids=[elem.id]))
                else:
                    blocks.append(TextBlock(content=elem.content, page=page.number, element_ids=[elem.id]))

        return blocks, synthetic_elements

    @staticmethod
    def _split_from_text(pages: List[Any]):
        """Fallback: split blocks from page content."""
        blocks = []
        table_content = ""
        last_page = None

        for page in pages:
            last_page = page

            for line in page.content.split('\n'):
                if table_content and not Chunker._is_table_line(line):
                    blocks.append(TableBlock(content=table_content, page=page.number))
                    table_content = ""

                if line.startswith("#"):
                    blocks.append(HeaderBlock(content=line, page=page.number))

                elif Chunker._is_table_line(line):
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

    def _chunk_blocks(self, blocks: List[BaseBlock], header: str = None, page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None, element_by_id: dict = None) -> List[Chunk]:
        """Converts the blocks to chunks"""
        page_elements = page_elements or {}
        display_page_map = display_page_map or {}
        page_contents = page_contents or {}
        element_by_id = element_by_id or {}
        chunks = []
        chunk_blocks = []
        num_tokens = 0

        for i, block in enumerate(blocks):
            next_block = blocks[i + 1] if i + 1 < len(blocks) else None

            if block.block_type == 'Text':
                chunk_blocks, num_tokens, chunks = self._process_text_block(
                    block, chunk_blocks, num_tokens, chunks, header, page_elements, display_page_map, page_contents, element_by_id
                )

            elif block.block_type == 'Table':
                chunk_blocks, num_tokens, chunks = self._process_table_block(
                    block, chunk_blocks, num_tokens, chunks, blocks, i, header, page_elements, display_page_map, page_contents, element_by_id
                )

            else:
                chunk_blocks, num_tokens, chunks = self._process_header_table_block(
                    block, chunk_blocks, num_tokens, chunks, next_block, header, page_elements, display_page_map, page_contents, element_by_id
                )

        if chunk_blocks:
            self._finalize_chunk(chunks, chunk_blocks, header, page_elements, display_page_map, page_contents, element_by_id)

        return chunks

    def _process_text_block(self, block: TextBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                            chunks: List[Chunk], header: str = None, page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None, element_by_id: dict = None):
        """Process a text block by breaking it into sentences if needed"""
        sentences = []
        sentences_tokens = 0

        for sentence in block.sentences:
            if num_tokens + sentences_tokens + sentence.tokens > self.chunk_size:
                if sentences:
                    new_block = TextBlock.from_sentences(
                        sentences=sentences,
                        page=block.page,
                        element_ids=block.element_ids
                    )
                    chunk_blocks.append(new_block)
                    num_tokens += sentences_tokens

                chunks, chunk_blocks, num_tokens = self._create_chunk(
                    chunks=chunks,
                    blocks=chunk_blocks,
                    header=header,
                    page_elements=page_elements,
                    display_page_map=display_page_map,
                    page_contents=page_contents,
                    element_by_id=element_by_id
                )

                sentences = [sentence]
                sentences_tokens = sentence.tokens

            else:
                sentences.append(sentence)
                sentences_tokens += sentence.tokens

        if sentences:
            new_block = TextBlock.from_sentences(sentences=sentences, page=block.page, element_ids=block.element_ids)
            chunk_blocks.append(new_block)
            num_tokens += sentences_tokens

        return chunk_blocks, num_tokens, chunks

    def _process_table_block(self, block: BaseBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                             chunks: List[Chunk], all_blocks: List[BaseBlock], block_idx: int, header: str = None, page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None, element_by_id: dict = None):
        """Process a table block with optional header backtrack.

        Note: Table splitting by token limit is now handled at the element level
        in _split_table_element, so blocks arriving here are already properly sized.
        """
        context, context_tokens = self._get_table_context(all_blocks, block_idx)

        chunk_blocks, num_tokens, chunks = self._add_table_block(
            table_block=block,
            context=context,
            context_tokens=context_tokens,
            chunk_blocks=chunk_blocks,
            num_tokens=num_tokens,
            chunks=chunks,
            header=header,
            page_elements=page_elements,
            display_page_map=display_page_map,
            page_contents=page_contents,
            element_by_id=element_by_id
        )

        return chunk_blocks, num_tokens, chunks

    def _add_table_block(self, table_block: TableBlock, context: List[BaseBlock], context_tokens: int,
                         chunk_blocks: List[BaseBlock], num_tokens: int, chunks: List[Chunk], header: str = None,
                         page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None,
                         element_by_id: dict = None) -> Tuple[List[BaseBlock], int, List[Chunk]]:
        """Attach a (possibly split) table block to the current chunk stream."""
        context_to_use = context if context and not self._has_context(chunk_blocks, context) else []
        context_to_use_tokens = context_tokens if context_to_use else 0

        if num_tokens + context_to_use_tokens + table_block.tokens > self.chunk_size:
            if chunk_blocks:
                chunks, chunk_blocks, num_tokens = self._create_chunk(
                    chunks=chunks,
                    blocks=chunk_blocks,
                    header=header,
                    page_elements=page_elements,
                    display_page_map=display_page_map,
                    page_contents=page_contents,
                    element_by_id=element_by_id
                )

            if context_to_use and chunks and len(chunks[-1].blocks) == len(context_to_use):
                if all(chunks[-1].blocks[i] == context_to_use[i] for i in range(len(context_to_use))):
                    chunks.pop()

            chunk_blocks = context_to_use + [table_block]
            num_tokens = context_to_use_tokens + table_block.tokens
        else:
            chunk_blocks.extend(context_to_use + [table_block])
            num_tokens += context_to_use_tokens + table_block.tokens

        return chunk_blocks, num_tokens, chunks

    @staticmethod
    def _has_context(chunk_blocks: List[BaseBlock], context: List[BaseBlock]) -> bool:
        """Return True if the chunk already starts with the provided context."""
        if not context or len(chunk_blocks) < len(context):
            return False
        return chunk_blocks[:len(context)] == context

    def _get_table_context(self, all_blocks: List[BaseBlock], block_idx: int) -> Tuple[List[BaseBlock], int]:
        """Backtrack short preceding blocks to carry into table chunks."""
        context: List[BaseBlock] = []
        context_tokens = 0
        count = 0
        current_page = all_blocks[block_idx].page if 0 <= block_idx < len(all_blocks) else None

        for j in range(block_idx - 1, -1, -1):
            prev = all_blocks[j]
            if prev.page != current_page:
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

        return context, context_tokens

    def _process_header_table_block(self, block: BaseBlock, chunk_blocks: List[BaseBlock], num_tokens: int,
                                    chunks: List[Chunk], next_block: BaseBlock, header: str = None, page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None, element_by_id: dict = None):
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
            chunks, chunk_blocks, num_tokens = self._create_chunk(
                chunks=chunks,
                blocks=chunk_blocks,
                header=header,
                page_elements=page_elements,
                display_page_map=display_page_map,
                page_contents=page_contents,
                element_by_id=element_by_id
            )
            chunk_blocks.append(block)
            num_tokens += block.tokens
        else:
            chunk_blocks.append(block)
            num_tokens += block.tokens

        return chunk_blocks, num_tokens, chunks

    def _finalize_chunk(self, chunks: List[Chunk], blocks: List[BaseBlock], header: str, page_elements: dict, display_page_map: dict, page_contents: dict, element_by_id: dict):
        """Create chunk with elements from the pages it spans"""
        chunk_pages = set(block.page for block in blocks)
        elements = self._select_elements_for_chunk(
            blocks=blocks,
            chunk_pages=chunk_pages,
            page_elements=page_elements,
            page_contents=page_contents,
            element_by_id=element_by_id
        )

        # Only include display_page_map if it has mappings, otherwise None for cleaner repr
        chunk_display_map = {k: v for k, v in display_page_map.items() if k in chunk_pages} if display_page_map else None

        chunks.append(Chunk(
            blocks=blocks,
            header=header,
            elements=elements,
            display_page_map=chunk_display_map if chunk_display_map else None,
            index=len(chunks)  # 0-based index
        ))

    def _create_chunk(self, chunks: List[Chunk], blocks: List[BaseBlock], header: str = None, page_elements: dict = None, display_page_map: dict = None, page_contents: dict = None, element_by_id: dict = None) -> Tuple[
        List[Chunk], List[BaseBlock], int]:
        """Creates a chunk and returns overlap blocks"""
        page_elements = page_elements or {}
        display_page_map = display_page_map or {}
        page_contents = page_contents or {}
        element_by_id = element_by_id or {}
        self._finalize_chunk(chunks, blocks, header, page_elements, display_page_map, page_contents, element_by_id)

        if not self.chunk_overlap:
            return chunks, [], 0

        overlap_tokens = 0
        overlap_blocks = []

        for block in reversed(blocks):
            if block.block_type == "Text":
                sentences = []

                for sentence in reversed(block.sentences):

                    if overlap_tokens + sentence.tokens > self.chunk_overlap:
                        text_block = TextBlock.from_sentences(
                            sentences=sentences,
                            page=block.page,
                            element_ids=block.element_ids
                        )
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

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize whitespace for fuzzy matching."""
        return re.sub(r"\s+", " ", text).strip().lower()

    def _find_block_span(self, blocks: List[BaseBlock], page_text: str) -> Tuple[Optional[int], Optional[int]]:
        """Find approximate start/end offsets of the blocks within the page.

        Uses exact match first, then a whitespace-normalized regex fallback so
        table minification or line-wrap differences still locate the span.
        """
        if not page_text:
            return None, None

        cursor = 0
        start = None
        end = None

        def find_with_fallback(text: str, haystack: str, start_pos: int) -> Tuple[Optional[int], Optional[int]]:
            """Exact search, else whitespace-tolerant regex."""
            idx = haystack.find(text, start_pos)
            if idx != -1:
                return idx, idx + len(text)

            # Build whitespace-tolerant pattern
            escaped = re.escape(text)
            pattern = re.sub(r"\\\s+", r"\\s+", escaped)
            m = re.search(pattern, haystack, flags=re.MULTILINE)
            if m:
                return m.start(), m.end()
            return None, None

        for blk in blocks:
            content = blk.content.strip()
            if not content:
                continue

            blk_start, blk_end = find_with_fallback(content, page_text, cursor)
            if blk_start is None:
                # Fallback: try searching from beginning
                blk_start, blk_end = find_with_fallback(content, page_text, 0)

            if blk_start is None:
                continue

            start = blk_start if start is None else min(start, blk_start)
            end = blk_end if end is None else max(end, blk_end)
            cursor = blk_end

        return start, end

    def _select_elements_for_chunk(self, blocks: List[BaseBlock], chunk_pages: set, page_elements: dict, page_contents: dict, element_by_id: dict) -> List[Element]:
        """Return elements for the chunk, preferring block-backed IDs, else offset fallback."""
        selected: List[Element] = []

        # Fast path: use element_ids carried on blocks
        ids: list[str] = []
        for blk in blocks:
            if blk.element_ids:
                ids.extend(blk.element_ids)

        if ids:
            seen = set()
            for eid in ids:
                if eid in seen:
                    continue
                seen.add(eid)
                elem = element_by_id.get(eid)
                if elem:
                    selected.append(elem)
            return selected

        # Fallback: use positional matching
        for page_num in sorted(chunk_pages):
            elems = page_elements.get(page_num) or []
            if not elems:
                continue

            page_text = page_contents.get(page_num, "")
            if not page_text:
                continue

            blocks_for_page = [b for b in blocks if b.page == page_num]
            start, end = self._find_block_span(blocks_for_page, page_text)
            if start is None or end is None:
                continue

            for elem in elems:
                if elem.content_start_offset is None or elem.content_end_offset is None:
                    continue
                if start <= elem.content_start_offset and elem.content_end_offset <= end:
                    selected.append(elem)

        return selected
