"""Pages to chunks of about chunk_size tokens, overlapping, each citing the elements it came from."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sec2md.chunker.blocks import BaseBlock, HeaderBlock, TableBlock, TextBlock, estimate_tokens
from sec2md.chunker.chunk import Chunk
from sec2md.models import Element


@dataclass
class _Run:
    """One split(): the chunks made so far, and the blocks (and tokens) of the one being filled."""
    header: Optional[str]
    display_pages: Dict[int, int]
    element_by_id: Dict[str, Element]
    chunks: List[Chunk] = field(default_factory=list)
    blocks: List[BaseBlock] = field(default_factory=list)
    tokens: int = 0


class Chunker:
    """Splits pages into chunks: text by sentence, tables whole (split by rows past max_table_tokens)
    with the short lines before them, headers kept with what follows."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128, max_table_tokens: int = 2048):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_table_tokens = max_table_tokens

    def split(self, pages: List[Any], header: str = None) -> List[Chunk]:
        """Chunk pages; `header` is prepended to each chunk's embedding_text."""
        element_by_id: Dict[str, Element] = {}
        display_pages: Dict[int, int] = {}
        for page in pages:
            for elem in getattr(page, "elements", None) or []:
                element_by_id[elem.id] = elem
            if getattr(page, "display_page", None) is not None:
                display_pages[page.number] = page.display_page

        if element_by_id:
            blocks, synthetic_elements = self._split_from_elements(pages)
            element_by_id.update(synthetic_elements)
        else:
            blocks = self._split_from_text(pages)

        run = _Run(header=header, display_pages=display_pages, element_by_id=element_by_id)
        for i, block in enumerate(blocks):
            if block.block_type == "Text":
                self._add_text(run, block)
            elif block.block_type == "Table":
                self._add_table(run, block, *self._table_context(blocks, i))
            else:
                self._add_header(run, block, blocks[i + 1] if i + 1 < len(blocks) else None)
        if run.blocks:
            self._close(run)
        return run.chunks

    def chunk_text(self, text: str) -> List[str]:
        """Chunk a single text string."""
        from sec2md.models import Page
        return [chunk.content for chunk in self.split(pages=[Page(number=0, content=text)])]

    # -- blocks -------------------------------------------------------------------------------------

    def _split_from_elements(self, pages: List[Any]) -> Tuple[List[BaseBlock], Dict[str, Element]]:
        """One block per element, in page order; an oversized table becomes several, each backed by
        a synthetic element '<id>:part-<n>' (returned with the blocks)."""
        blocks: List[BaseBlock] = []
        synthetic_elements: Dict[str, Element] = {}
        for page in pages:
            elems = getattr(page, "elements", None)
            if not elems:
                blocks.extend(self._split_from_text([page]))
                continue
            # By offset when known, else in element order
            ordered = sorted(enumerate(elems), key=lambda pair: (
                pair[1].content_start_offset if pair[1].content_start_offset is not None else float("inf"), pair[0]))
            for _, elem in ordered:
                kind = (elem.kind or "").lower()
                if kind == "table":
                    for part, block in self._split_table_element(elem, page.number):
                        if part.id != elem.id:
                            synthetic_elements[part.id] = part
                        blocks.append(block)
                elif kind == "header":
                    blocks.append(HeaderBlock(content=elem.content, page=page.number, element_ids=[elem.id]))
                else:
                    blocks.append(TextBlock(content=elem.content, page=page.number, element_ids=[elem.id]))
        return blocks, synthetic_elements

    @staticmethod
    def _split_from_text(pages: List[Any]) -> List[BaseBlock]:
        """Blocks from page text: '#' lines are headers, runs of '|' lines tables, other lines text."""
        blocks: List[BaseBlock] = []
        table_content = ""
        for page in pages:
            for line in page.content.split("\n"):
                if table_content and "|" not in line:
                    blocks.append(TableBlock(content=table_content, page=page.number))
                    table_content = ""
                if line.startswith("#"):
                    blocks.append(HeaderBlock(content=line, page=page.number))
                elif "|" in line:
                    table_content += f"{line}\n"
                else:
                    blocks.append(TextBlock(content=line, page=page.number))
        if table_content and pages:
            blocks.append(TableBlock(content=table_content, page=pages[-1].number))
        return blocks

    def _split_table_element(self, elem: Element, page_number: int) -> List[Tuple[Element, TableBlock]]:
        """A table over max_table_tokens, split by rows: each part repeats the header rows and marks
        the rows cut before and after it with a '...' row."""
        content = elem.content
        lines = [line for line in content.split("\n") if line.strip()]
        if not self.max_table_tokens or estimate_tokens(content) <= self.max_table_tokens or len(lines) <= 2:
            return [(elem, TableBlock(content=content, page=page_number, element_ids=[elem.id]))]

        header_line, separator_line, data_rows = lines[0], lines[1], lines[2:]
        num_cols = max(1, len([cell for cell in header_line.strip().split("|") if cell.strip()]))
        ellipsis_row = "|" + "|".join(["..."] * num_cols) + "|"

        results: List[Tuple[Element, TableBlock]] = []
        row_idx = 0
        while row_idx < len(data_rows):
            base_lines = [header_line, separator_line] + ([ellipsis_row] if row_idx > 0 else [])
            segment_rows: List[str] = []
            while row_idx < len(data_rows):
                candidate = base_lines + segment_rows + [data_rows[row_idx]]
                if row_idx < len(data_rows) - 1:
                    candidate.append(ellipsis_row)
                if estimate_tokens("\n".join(candidate)) > self.max_table_tokens:
                    if not segment_rows:  # a single row over budget goes alone
                        segment_rows.append(data_rows[row_idx])
                        row_idx += 1
                    break
                segment_rows.append(data_rows[row_idx])
                row_idx += 1

            segment_content = "\n".join(base_lines + segment_rows + ([ellipsis_row] if row_idx < len(data_rows) else []))
            segment_id = f"{elem.id}:part-{len(results)}"
            segment_element = Element(
                id=segment_id, content=segment_content, kind=elem.kind,
                page_start=elem.page_start, page_end=elem.page_end,
                content_start_offset=elem.content_start_offset, content_end_offset=elem.content_end_offset,
            )
            results.append((segment_element, TableBlock(content=segment_content, page=page_number,
                                                        element_ids=[segment_id])))
        return results

    # -- filling chunks ---------------------------------------------------------------------------------

    def _add_text(self, run: _Run, block: TextBlock) -> None:
        """Sentence by sentence; a sentence that would overflow the chunk starts the next one."""
        sentences = []
        sentences_tokens = 0
        for sentence in block.sentences:
            if run.tokens + sentences_tokens + sentence.tokens > self.chunk_size:
                if sentences:
                    run.blocks.append(TextBlock.from_sentences(sentences, page=block.page, element_ids=block.element_ids))
                    run.tokens += sentences_tokens
                if run.blocks:
                    self._emit(run)
                sentences = [sentence]
                sentences_tokens = sentence.tokens
            else:
                sentences.append(sentence)
                sentences_tokens += sentence.tokens
        if sentences:
            run.blocks.append(TextBlock.from_sentences(sentences, page=block.page, element_ids=block.element_ids))
            run.tokens += sentences_tokens

    @staticmethod
    def _table_context(blocks: List[BaseBlock], block_idx: int) -> Tuple[List[BaseBlock], int]:
        """The short lines before a table on its page (a header, or up to two text lines; 128 tokens
        at most) that travel with it into its chunk."""
        context: List[BaseBlock] = []
        context_tokens = 0
        text_lines = 0
        for j in range(block_idx - 1, -1, -1):
            prev = blocks[j]
            if prev.page != blocks[block_idx].page:
                break
            if prev.block_type == "Header":
                if context_tokens + prev.tokens <= 128:
                    context.insert(0, prev)
                    context_tokens += prev.tokens
                break
            if prev.block_type == "Text" and prev.content.strip():
                text_lines += 1
                if text_lines > 2 or context_tokens + prev.tokens > 128:
                    break
                context.insert(0, prev)
                context_tokens += prev.tokens
        return context, context_tokens

    def _add_table(self, run: _Run, table: TableBlock, context: List[BaseBlock], context_tokens: int) -> None:
        if not context or run.blocks[:len(context)] == context:  # no context, or the chunk already starts with it
            context, context_tokens = [], 0
        if run.tokens + context_tokens + table.tokens > self.chunk_size:
            if run.blocks:
                self._emit(run)
            if context and run.chunks and run.chunks[-1].blocks == context:
                run.chunks.pop()  # the chunk just closed was only this table's context
            run.blocks = context + [table]
            run.tokens = context_tokens + table.tokens
        else:
            run.blocks.extend(context + [table])
            run.tokens += context_tokens + table.tokens

    def _add_header(self, run: _Run, block: BaseBlock, next_block: Optional[BaseBlock]) -> None:
        # A header before a table stays with a chunk that has barely started.
        keep = next_block is not None and next_block.block_type == "Table" and run.tokens < self.chunk_overlap
        if run.blocks and not keep and run.tokens + block.tokens > self.chunk_size:
            self._emit(run)
        run.blocks.append(block)
        run.tokens += block.tokens

    # -- closing chunks -----------------------------------------------------------------------------

    def _close(self, run: _Run) -> None:
        """The blocks being filled become a chunk, citing their blocks' elements."""
        pages = {block.page for block in run.blocks}
        ids = dict.fromkeys(eid for block in run.blocks for eid in block.element_ids or [])
        display = {k: v for k, v in run.display_pages.items() if k in pages}
        run.chunks.append(Chunk(
            blocks=run.blocks,
            header=run.header,
            elements=[run.element_by_id[eid] for eid in ids if eid in run.element_by_id],
            display_page_map=display or None,
            index=len(run.chunks),
        ))

    def _emit(self, run: _Run) -> None:
        """Close the chunk; the next one starts with the overlap."""
        self._close(run)
        run.blocks, run.tokens = self._overlap(run.blocks)

    def _overlap(self, blocks: List[BaseBlock]) -> Tuple[List[BaseBlock], int]:
        """The tail of a closed chunk that opens the next one: up to chunk_overlap tokens, whole
        sentences and whole tables/headers, taken from the end."""
        if not self.chunk_overlap:
            return [], 0
        overlap_tokens = 0
        overlap_blocks: List[BaseBlock] = []
        for block in reversed(blocks):
            if block.block_type == "Text":
                sentences = []
                for sentence in reversed(block.sentences):
                    if overlap_tokens + sentence.tokens > self.chunk_overlap:
                        if sentences:
                            overlap_blocks.insert(0, TextBlock.from_sentences(
                                sentences, page=block.page, element_ids=block.element_ids))
                        return overlap_blocks, overlap_tokens
                    sentences.insert(0, sentence)
                    overlap_tokens += sentence.tokens
            else:
                if overlap_tokens + block.tokens > self.chunk_overlap:
                    return overlap_blocks, overlap_tokens
                overlap_blocks.insert(0, block)
                overlap_tokens += block.tokens
        return [], 0
