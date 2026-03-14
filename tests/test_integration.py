"""Integration tests: diff current output against golden files.

Setup (one-time):
    python tests/generate_golden.py
    # inspect tests/golden/, commit when satisfied

Run:
    pytest -m integration

Uses the AAPL 10-K from the README quickstart as the single fixture.
"""

import json
import difflib
from pathlib import Path

import pytest

import sec2md
from sec2md import Item10K

GOLDEN_DIR = Path(__file__).parent / "golden"
CACHE_DIR = Path(__file__).parent / ".cache"


def _skip_if_missing():
    if not (CACHE_DIR / "aapl_10k.html").exists():
        pytest.skip("No cached HTML. Run: python tests/generate_golden.py")
    if not (GOLDEN_DIR / "manifest.json").exists():
        pytest.skip("No golden files. Run: python tests/generate_golden.py")


def _load_html() -> str:
    return (CACHE_DIR / "aapl_10k.html").read_text(encoding="utf-8")


def _load_golden(filename: str) -> str:
    path = GOLDEN_DIR / filename
    if not path.exists():
        pytest.skip(f"Missing golden file: {path}")
    return path.read_text(encoding="utf-8")


def _load_manifest() -> dict:
    return json.loads(_load_golden("manifest.json"))


def _assert_md_equal(expected: str, actual: str, context: str):
    """Assert markdown matches golden, print unified diff on failure."""
    if expected == actual:
        return
    diff = list(difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile=f"golden/{context}",
        tofile=f"current/{context}",
        n=3,
    ))
    diff_text = "".join(diff)
    if len(diff_text) > 5000:
        diff_text = diff_text[:5000] + "\n... (truncated)"
    pytest.fail(f"Markdown diff in {context}:\n{diff_text}")


# ---------------------------------------------------------------------------
# Full markdown output
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullMarkdown:
    def test_matches_golden(self):
        _skip_if_missing()
        html = _load_html()
        golden = _load_golden("full.md")
        actual = sec2md.convert_to_markdown(html)
        _assert_md_equal(golden, actual, "full.md")


# ---------------------------------------------------------------------------
# Section extraction (README example)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSections:
    @pytest.fixture(autouse=True)
    def setup(self):
        _skip_if_missing()
        self.html = _load_html()
        self.manifest = _load_manifest()
        self.pages = sec2md.convert_to_markdown(self.html, return_pages=True)
        self.sections = sec2md.extract_sections(self.pages, filing_type="10-K")

    def test_page_count(self):
        assert len(self.pages) == self.manifest["page_count"]

    def test_section_count(self):
        assert len(self.sections) == self.manifest["section_count"]

    def test_section_items_match(self):
        actual = [s.item for s in self.sections]
        expected = [s["item"] for s in self.manifest["sections"]]
        assert actual == expected

    def test_section_page_ranges(self):
        for section, expected in zip(self.sections, self.manifest["sections"]):
            assert list(section.page_range) == expected["page_range"], (
                f"{section.item}: {list(section.page_range)} != {expected['page_range']}"
            )

    def test_section_token_counts_stable(self):
        for section, expected in zip(self.sections, self.manifest["sections"]):
            tolerance = max(10, int(expected["tokens"] * 0.05))
            assert abs(section.tokens - expected["tokens"]) <= tolerance, (
                f"{section.item}: {section.tokens} vs expected {expected['tokens']}"
            )

    def test_each_section_markdown_matches(self):
        for section in self.sections:
            safe_name = (section.item or "no_item").replace(" ", "_").lower()
            golden_path = GOLDEN_DIR / f"{safe_name}.md"
            if not golden_path.exists():
                continue
            golden = golden_path.read_text(encoding="utf-8")
            actual = section.markdown()
            _assert_md_equal(golden, actual, f"{safe_name}.md")


# ---------------------------------------------------------------------------
# get_section by enum (README example)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestGetSection:
    def test_risk_factors_by_enum(self):
        _skip_if_missing()
        html = _load_html()
        pages = sec2md.convert_to_markdown(html, return_pages=True)
        sections = sec2md.extract_sections(pages, filing_type="10-K")
        risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
        assert risk is not None
        assert risk.item == "ITEM 1A"
        assert risk.tokens > 100

        golden = _load_golden("item_1a.md")
        _assert_md_equal(golden, risk.markdown(), "item_1a.md")


# ---------------------------------------------------------------------------
# Chunking (README examples)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestChunking:
    def test_chunk_count_stable(self):
        _skip_if_missing()
        manifest = _load_manifest()
        html = _load_html()
        pages = sec2md.convert_to_markdown(html, return_pages=True)
        chunks = sec2md.chunk_pages(pages, chunk_size=512)
        assert len(chunks) == manifest["chunk_count"]

    def test_no_empty_chunks(self):
        _skip_if_missing()
        html = _load_html()
        pages = sec2md.convert_to_markdown(html, return_pages=True)
        chunks = sec2md.chunk_pages(pages, chunk_size=512)
        for i, chunk in enumerate(chunks):
            assert chunk.content.strip(), f"Chunk {i} is empty"
            assert len(chunk.blocks) > 0

    def test_risk_section_chunks_with_header(self):
        _skip_if_missing()
        manifest = _load_manifest()
        html = _load_html()
        pages = sec2md.convert_to_markdown(html, return_pages=True)
        sections = sec2md.extract_sections(pages, filing_type="10-K")
        risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
        header = "Apple Inc. (AAPL)\nForm 10-K | FY 2024 | Risk Factors"
        chunks = sec2md.chunk_section(risk, chunk_size=512, header=header)
        assert len(chunks) == manifest["risk_chunk_count"]
        for chunk in chunks:
            assert chunk.embedding_text.startswith("Apple Inc.")


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestInvariants:
    @pytest.fixture(autouse=True)
    def setup(self):
        _skip_if_missing()
        self.html = _load_html()
        self.pages = sec2md.convert_to_markdown(self.html, return_pages=True)

    def test_page_numbers_sequential(self):
        numbers = [p.number for p in self.pages]
        assert numbers == list(range(1, len(self.pages) + 1))

    def test_element_ids_unique(self):
        pages = sec2md.parse_filing(self.html, include_elements=True)
        all_ids = []
        for p in pages:
            if p.elements:
                all_ids.extend(e.id for e in p.elements)
        assert len(all_ids) == len(set(all_ids))

    def test_tables_present(self):
        has_table = any("|" in p.content and "---" in p.content for p in self.pages)
        assert has_table
