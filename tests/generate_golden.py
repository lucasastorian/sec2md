#!/usr/bin/env python3
"""Fetch the AAPL 10-K from the README and generate golden output.

Run once, inspect tests/golden/, commit when satisfied.

Usage:
    python tests/generate_golden.py
"""

import json
from pathlib import Path

import requests

import sec2md
from sec2md import Item10K

GOLDEN_DIR = Path(__file__).parent / "golden"
CACHE_DIR = Path(__file__).parent / ".cache"
USER_AGENT = "sec2md-tests integration@sec2md.dev"

# The exact URL from the README quickstart
AAPL_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"


def fetch_html() -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / "aapl_10k.html"

    if cache_path.exists():
        print(f"[cache hit] {cache_path}")
        return cache_path.read_text(encoding="utf-8")

    print(f"[fetching] {AAPL_URL}")
    resp = requests.get(AAPL_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    cache_path.write_text(resp.text, encoding="utf-8")
    return resp.text


def main():
    html = fetch_html()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    # Full markdown (the README quickstart output)
    md = sec2md.convert_to_markdown(html)
    (GOLDEN_DIR / "full.md").write_text(md, encoding="utf-8")
    print(f"full.md: {len(md):,} chars")

    # Pages + sections (README section extraction example)
    pages = sec2md.convert_to_markdown(html, return_pages=True)
    sections = sec2md.extract_sections(pages, filing_type="10-K")

    manifest = {
        "page_count": len(pages),
        "section_count": len(sections),
        "sections": [],
    }

    for section in sections:
        section_md = section.markdown()
        safe_name = (section.item or "no_item").replace(" ", "_").lower()
        (GOLDEN_DIR / f"{safe_name}.md").write_text(section_md, encoding="utf-8")

        manifest["sections"].append({
            "item": section.item,
            "part": section.part,
            "title": section.item_title,
            "page_range": list(section.page_range),
            "tokens": section.tokens,
            "chars": len(section_md),
        })
        print(f"  {safe_name}.md: {len(section_md):,} chars, {section.tokens:,} tokens")

    # Chunking (README chunking example)
    chunks = sec2md.chunk_pages(pages, chunk_size=512)
    manifest["chunk_count"] = len(chunks)

    # Section chunking with header (README RAG header example)
    risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
    header = "Apple Inc. (AAPL)\nForm 10-K | FY 2024 | Risk Factors"
    risk_chunks = sec2md.chunk_section(risk, chunk_size=512, header=header)
    manifest["risk_chunk_count"] = len(risk_chunks)

    (GOLDEN_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"\nmanifest.json: {len(sections)} sections, {len(pages)} pages, "
          f"{len(chunks)} chunks, {len(risk_chunks)} risk chunks")
    print("\nDone. Inspect tests/golden/ and commit when satisfied.")


if __name__ == "__main__":
    main()
