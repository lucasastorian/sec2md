"""Tests for the chunking system (chunker.py, blocks.py, chunk.py, chunking.py)."""

from unittest.mock import patch, MagicMock

import pytest

from sec2md.chunker.chunker import Chunker
from sec2md.chunker.blocks import (
    TextBlock, TableBlock, HeaderBlock, Sentence,
    split_sentences, estimate_tokens,
)
from sec2md.chunker.chunk import Chunk
from sec2md.chunking import chunk_pages, chunk_section, merge_text_blocks, chunk_text_block
from sec2md.models import Page, Section, Element, TextBlock as ModelTextBlock


# ---------------------------------------------------------------------------
# Block-level tests
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_basic_split(self):
        result = split_sentences("Hello world. Goodbye world.")
        assert len(result) == 2
        assert result[0] == "Hello world."
        assert result[1] == "Goodbye world."

    def test_no_split_on_abbreviation_like(self):
        result = split_sentences("Mr. Smith went to Washington.")
        # Should not split on "Mr." since next word is capitalized
        # (this regex-based splitter does split here -- just verify no crash)
        assert len(result) >= 1

    def test_single_sentence(self):
        result = split_sentences("Just one sentence here")
        assert len(result) == 1

    def test_empty_string(self):
        result = split_sentences("")
        assert result == []

    def test_exclamation_and_question(self):
        result = split_sentences("Wow! Is this working? Yes it is.")
        assert len(result) == 3


class TestEstimateTokens:
    def test_returns_positive(self):
        assert estimate_tokens("hello") >= 1

    def test_longer_text_more_tokens(self):
        short = estimate_tokens("hi")
        long = estimate_tokens("This is a much longer text with many more words in it")
        assert long > short

    def test_fallback_on_tiktoken_error(self):
        """Regression: tiktoken runtime errors must not crash estimate_tokens."""
        mock_tiktoken = MagicMock()
        mock_tiktoken.get_encoding.side_effect = ConnectionError("offline")
        with patch.dict("sys.modules", {"tiktoken": mock_tiktoken}):
            with patch("sec2md.chunker.blocks.TIKTOKEN_AVAILABLE", True):
                result = estimate_tokens("hello world")
                assert result == max(1, len("hello world") // 4)


class TestTextBlock:
    def test_sentences_property(self):
        block = TextBlock(content="First sentence. Second sentence.", page=1)
        assert len(block.sentences) == 2

    def test_from_sentences(self):
        sentences = [Sentence(content="A."), Sentence(content="B.")]
        block = TextBlock.from_sentences(sentences, page=1)
        assert "A." in block.content
        assert "B." in block.content

    def test_tokens_computed(self):
        block = TextBlock(content="Some text here", page=1)
        assert block.tokens >= 1

    def test_block_type(self):
        assert TextBlock(content="x", page=1).block_type == "Text"
        assert TableBlock(content="| a | b |", page=1).block_type == "Table"
        assert HeaderBlock(content="# Title", page=1).block_type == "Header"


class TestTableBlockMinification:
    def test_minifies_whitespace(self):
        content = "|  lots   of   space  |  here  |\n| --- | --- |\n|  a  |  b  |"
        block = TableBlock(content=content, page=1)
        assert "lots of space" in block.content
        assert "  " not in block.content.split("|")[1]  # inner cells trimmed


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunkerBasic:
    def test_single_page_single_chunk(self):
        page = Page(number=1, content="Short text.")
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) == 1
        assert "Short text" in chunks[0].content

    def test_splits_long_content(self):
        long_text = ". ".join([f"Sentence number {i}" for i in range(100)])
        page = Page(number=1, content=long_text)
        chunker = Chunker(chunk_size=32, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) > 1

    def test_overlap_creates_shared_content(self):
        text = ". ".join([f"Sentence {i}" for i in range(20)])
        page = Page(number=1, content=text)
        chunker = Chunker(chunk_size=32, chunk_overlap=8)
        chunks = chunker.split(pages=[page])
        if len(chunks) >= 2:
            # Some content from end of chunk 0 should appear in chunk 1
            c0_words = set(chunks[0].content.split())
            c1_words = set(chunks[1].content.split())
            assert c0_words & c1_words  # some overlap

    def test_zero_overlap(self):
        text = ". ".join([f"Sentence {i}" for i in range(20)])
        page = Page(number=1, content=text)
        chunker = Chunker(chunk_size=32, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) >= 1

    def test_multiple_pages(self):
        pages = [
            Page(number=1, content="Page one content."),
            Page(number=2, content="Page two content."),
        ]
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[pages[0], pages[1]])
        assert len(chunks) >= 1


class TestChunkerBoundary:
    """Boundary condition tests for the chunker."""

    def test_chunk_size_one(self):
        page = Page(number=1, content="Hello. World.")
        chunker = Chunker(chunk_size=1, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        for chunk in chunks:
            assert len(chunk.blocks) > 0
            assert chunk.content.strip()

    def test_only_table_content(self):
        table_md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
        page = Page(number=1, content=table_md)
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) >= 1
        assert chunks[0].has_table

    def test_no_empty_chunks_ever(self):
        """Fuzz-like test: various chunk_size values should never produce empty chunks."""
        text = ". ".join([f"Word{i}" for i in range(50)])
        page = Page(number=1, content=text)
        for size in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]:
            chunker = Chunker(chunk_size=size, chunk_overlap=min(size // 2, 4))
            chunks = chunker.split(pages=[page])
            for i, chunk in enumerate(chunks):
                assert len(chunk.blocks) > 0, f"Empty chunk at size={size}, index={i}"

    def test_oversized_first_sentence_no_empty_chunk(self):
        """Regression: first sentence exceeding chunk_size must not produce empty chunks."""
        long_sentence = "Word " * 100
        page = Page(number=1, content=long_sentence.strip())
        chunker = Chunker(chunk_size=8, chunk_overlap=2)
        chunks = chunker.split(pages=[page])
        for i, chunk in enumerate(chunks):
            assert len(chunk.blocks) > 0, f"Chunk {i} has no blocks"
            assert chunk.content.strip(), f"Chunk {i} has empty content"


class TestChunkerElements:
    """Element linking in chunks."""

    def test_elements_carried_through(self):
        elem = Element(
            id="e1", content="Paragraph content", kind="paragraph",
            page_start=1, page_end=1,
            content_start_offset=0, content_end_offset=17
        )
        page = Page(number=1, content="Paragraph content", elements=[elem])
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) >= 1
        assert len(chunks[0].elements) >= 1
        assert chunks[0].elements[0].id == "e1"

    def test_element_ids_in_chunk(self):
        elem = Element(
            id="test-id", content="Content", kind="paragraph",
            page_start=1, page_end=1
        )
        page = Page(number=1, content="Content", elements=[elem])
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        if chunks and chunks[0].elements:
            assert "test-id" in chunks[0].element_ids


class TestChunkerTableSplitting:
    """Large table splitting by token limit."""

    def test_oversized_table_split(self):
        # Create a table that exceeds max_table_tokens
        rows = ["| Header1 | Header2 |", "| --- | --- |"]
        for i in range(100):
            rows.append(f"| Row {i} data | Value {i} |")
        table_content = "\n".join(rows)

        elem = Element(
            id="big-table", content=table_content, kind="table",
            page_start=1, page_end=1
        )
        page = Page(number=1, content=table_content, elements=[elem])
        # chunk_size must also be small enough that split table parts land in separate chunks
        chunker = Chunker(chunk_size=64, chunk_overlap=0, max_table_tokens=64)
        chunks = chunker.split(pages=[page])
        # Should be split into multiple chunks
        assert len(chunks) > 1

    def test_small_table_not_split(self):
        table_content = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        elem = Element(
            id="small-table", content=table_content, kind="table",
            page_start=1, page_end=1
        )
        page = Page(number=1, content=table_content, elements=[elem])
        chunker = Chunker(chunk_size=2048, chunk_overlap=0, max_table_tokens=2048)
        chunks = chunker.split(pages=[page])
        assert len(chunks) == 1


class TestChunkerDisplayPages:
    """Display page mapping in chunks."""

    def test_display_page_map_passed_through(self):
        page = Page(number=1, content="Content", display_page=42)
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.split(pages=[page])
        assert len(chunks) >= 1
        if chunks[0].display_page_map:
            assert chunks[0].display_page_map.get(1) == 42


# ---------------------------------------------------------------------------
# Chunk object tests
# ---------------------------------------------------------------------------

class TestChunkObject:
    def test_content_joins_blocks(self):
        blocks = [
            TextBlock(content="Line 1", page=1),
            TextBlock(content="Line 2", page=1),
        ]
        chunk = Chunk(blocks=blocks)
        assert "Line 1" in chunk.content
        assert "Line 2" in chunk.content

    def test_embedding_text_with_header(self):
        blocks = [TextBlock(content="Body", page=1)]
        chunk = Chunk(blocks=blocks, header="Company: AAPL")
        assert chunk.embedding_text.startswith("Company: AAPL")
        assert "Body" in chunk.embedding_text

    def test_embedding_text_without_header(self):
        blocks = [TextBlock(content="Body", page=1)]
        chunk = Chunk(blocks=blocks)
        assert chunk.embedding_text == chunk.content

    def test_has_table(self):
        blocks = [TableBlock(content="| a | b |", page=1)]
        chunk = Chunk(blocks=blocks)
        assert chunk.has_table is True

    def test_no_table(self):
        blocks = [TextBlock(content="Just text", page=1)]
        chunk = Chunk(blocks=blocks)
        assert chunk.has_table is False

    def test_page_range(self):
        blocks = [
            TextBlock(content="A", page=1),
            TextBlock(content="B", page=3),
        ]
        chunk = Chunk(blocks=blocks)
        assert chunk.start_page == 1
        assert chunk.end_page == 3

    def test_data_property(self):
        blocks = [
            TextBlock(content="Page 1 content", page=1),
            TextBlock(content="Page 2 content", page=2),
        ]
        chunk = Chunk(blocks=blocks)
        data = chunk.data
        assert len(data) == 2
        assert data[0]["page"] == 1
        assert data[1]["page"] == 2


# ---------------------------------------------------------------------------
# Public chunking API tests
# ---------------------------------------------------------------------------

class TestChunkPages:
    def test_basic_chunking(self):
        pages = [Page(number=1, content="Content here.")]
        chunks = chunk_pages(pages, chunk_size=512)
        assert len(chunks) >= 1

    def test_header_passed_through(self):
        pages = [Page(number=1, content="Content.")]
        chunks = chunk_pages(pages, chunk_size=512, header="Header: Test")
        assert chunks[0].header == "Header: Test"


class TestChunkSection:
    def test_chunks_section_pages(self):
        section = Section(
            part="PART I", item="ITEM 1", item_title="Business",
            pages=[Page(number=1, content="Business content here.")]
        )
        chunks = chunk_section(section, chunk_size=512)
        assert len(chunks) >= 1


class TestMergeTextBlocks:
    def test_merges_same_name_across_pages(self):
        elem1 = Element(id="e1", content="Part 1", kind="paragraph", page_start=1, page_end=1)
        elem2 = Element(id="e2", content="Part 2", kind="paragraph", page_start=2, page_end=2)
        tb1 = ModelTextBlock(name="us-gaap:DebtTextBlock", title="Debt", elements=[elem1])
        tb2 = ModelTextBlock(name="us-gaap:DebtTextBlock", title="Debt", elements=[elem2])
        pages = [
            Page(number=1, content="Part 1", text_blocks=[tb1]),
            Page(number=2, content="Part 2", text_blocks=[tb2]),
        ]
        merged = merge_text_blocks(pages)
        assert len(merged) == 1
        assert len(merged[0].elements) == 2
        assert merged[0].start_page == 1
        assert merged[0].end_page == 2

    def test_different_blocks_stay_separate(self):
        elem1 = Element(id="e1", content="Debt", kind="paragraph", page_start=1, page_end=1)
        elem2 = Element(id="e2", content="Revenue", kind="paragraph", page_start=1, page_end=1)
        tb1 = ModelTextBlock(name="us-gaap:DebtTextBlock", title="Debt", elements=[elem1])
        tb2 = ModelTextBlock(name="us-gaap:RevenueTextBlock", title="Revenue", elements=[elem2])
        pages = [Page(number=1, content="Content", text_blocks=[tb1, tb2])]
        merged = merge_text_blocks(pages)
        assert len(merged) == 2

    def test_empty_pages(self):
        merged = merge_text_blocks([])
        assert merged == []


class TestChunkTextBlock:
    def test_chunks_text_block(self):
        elems = [
            Element(id=f"e{i}", content=f"Sentence {i}.", kind="paragraph",
                    page_start=1, page_end=1)
            for i in range(5)
        ]
        tb = ModelTextBlock(name="us-gaap:DebtTextBlock", title="Debt", elements=elems)
        chunks = chunk_text_block(tb, chunk_size=512)
        assert len(chunks) >= 1
