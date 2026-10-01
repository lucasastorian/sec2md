"""Golden snapshots of the fixture filings: each one's markdown pages (tests/golden/<name>.md) and
the structure built on them (tests/golden/<name>.json: elements, XBRL text blocks, sections, chunks,
table cells lost). After an intended output change, regenerate and review the diff:

    python -m tests.snapshot && git diff tests/golden

Fixtures (tests/fixtures/<name>.html.gz, EDGAR primary documents) and what each one covers:

    aapl_10k              Apple 10-K FY2024 (0000320193-24-000123): Workiva iXBRL, the README examples
    idaho_strategic_10q   Idaho Strategic Resources 10-Q (0001654954-26-007547): page breaks inside
                          per-page footer tables (was one page before 0.1.24), XBRL text blocks
    cable_one_8k          Cable One 8-K (0000950157-26-001036): 8-K items, filing-agent comments
    apnimed_ex99          Apnimed EX-99 press release (from 0001193125-26-385355)
    techprecision_10q     TechPrecision 10-Q (0001104659-26-095944): position:absolute layout and
                          pseudo-tables (absolute_table_parser)
    general_mills_10q     General Mills 10-Q (0001628280-26-063201): Workiva print layout, one
                          content-visibility container per page, furniture placed by a CSS variable
    quantum_biopharma_6k  Quantum Biopharma 6-K (0001185185-26-003794): uppercase legacy-style HTML
"""
from __future__ import annotations

import functools
import gzip
import json
import re
from pathlib import Path

import sec2md
from sec2md import Parser
from sec2md.table_parser import TableParser

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

# fixture -> filing type for section extraction (None: no sections)
FIXTURES = {
    "aapl_10k": "10-K",
    "idaho_strategic_10q": "10-Q",
    "cable_one_8k": "8-K",
    "apnimed_ex99": None,
    "techprecision_10q": "10-Q",
    "general_mills_10q": "10-Q",
    "quantum_biopharma_6k": None,
}


def load_html(name: str) -> str:
    return gzip.decompress((FIXTURE_DIR / f"{name}.html.gz").read_bytes()).decode("utf-8")


@functools.lru_cache(maxsize=None)
def parse(name: str):
    """(pages, sections, chunks, annotated html) for a fixture, parsed once per test session."""
    parser = Parser(load_html(name))
    pages = parser.get_pages()
    ftype = FIXTURES[name]
    sections = sec2md.extract_sections(pages, filing_type=ftype) if ftype else []
    return pages, sections, sec2md.chunk_pages(pages), parser.html()


def lost_cells(html: str) -> int:
    """Non-trivial cell texts of visible tables (2+ rows) missing from the table's markdown."""
    from bs4 import BeautifulSoup

    norm = lambda t: re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()
    trivial = {"", "$", "%", "(", ")", "•", "●", "◦", "▪", "·", "-", "–", "—"}
    lost = 0
    for t in BeautifulSoup(html, "lxml").find_all("table"):
        hidden = any("display:none" in (a.get("style") or "").replace(" ", "").lower() for a in t.parents)
        if t.find_parent("table") or hidden or len(t.find_all("tr")) < 2:
            continue
        md = norm(TableParser(t).to_markdown().replace("\\|", " ").replace("|", " ").replace("**", ""))
        lost += sum(c not in md for c in {norm(td.get_text(" ")) for td in t.find_all(["td", "th"])} - trivial)
    return lost


def render(name: str) -> tuple[str, dict]:
    """The golden markdown (pages delimited by <!-- page N -->) and the golden structure."""
    pages, sections, chunks, _ = parse(name)
    md = "".join(f"<!-- page {p.number} -->\n{p.content}\n" for p in pages)
    structure = {
        "pages": len(pages),
        "display_pages": [[p.number, p.display_page] for p in pages if p.display_page is not None],
        "elements": [
            f"{e.id} {e.kind} {e.content_start_offset}:{e.content_end_offset}" + (f" {' '.join(e.tags)}" if e.tags else "")
            for p in pages for e in p.elements or []
        ],
        "text_blocks": [f"p{p.number} {tb.name} | {tb.title} | {len(tb.elements)}"
                        for p in pages for tb in p.text_blocks or []],
        "sections": [
            {"part": s.part, "item": s.item, "title": s.item_title, "pages": list(s.page_range),
             "tokens": s.tokens, "head": s.markdown()[:60], "tail": s.markdown()[-60:]}
            for s in sections
        ],
        "chunks": [f"{c.index} p{c.start_page}-{c.end_page} {c.num_tokens}t "
                   f"{c.element_ids[0] if c.element_ids else '-'}..{c.element_ids[-1] if c.element_ids else '-'}"
                   for c in chunks],
        "lost_cells": lost_cells(load_html(name)),
    }
    return md, structure


def main() -> None:
    for name in FIXTURES:
        md, structure = render(name)
        (GOLDEN_DIR / f"{name}.md").write_text(md, encoding="utf-8")
        (GOLDEN_DIR / f"{name}.json").write_text(json.dumps(structure, indent=1, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
        print(f"{name}: {structure['pages']} pages, {len(structure['elements'])} elements, "
              f"{len(structure['sections'])} sections, {len(structure['chunks'])} chunks, "
              f"{structure['lost_cells']} cells lost")


if __name__ == "__main__":
    main()
