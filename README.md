# sec2md

[![PyPI](https://img.shields.io/pypi/v/sec2md.svg)](https://pypi.org/project/sec2md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-readthedocs-blue.svg)](https://sec2md.readthedocs.io)

Transform messy SEC filings into clean, structured Markdown.
**Built for AI. Optimized for retrieval. Ready for production.**

![Before and After Comparison](comparison.png)
*Apple 10-K: Raw SEC HTML (left) vs. sec2md output (right)*

---

## The Problem

SEC filings are the worst documents you'll ever feed to an LLM.

200 pages of deeply nested HTML, XBRL tags, inline CSS, invisible elements, tables-within-tables, and PDF-to-HTML artifacts — all wrapped in markup that was designed for browser rendering, not machine comprehension.

When you throw this at a standard parser:

- **Tables break** — Financial statements become garbled text. Your model hallucinates numbers.
- **Pages vanish** — Can't cite sources. Can't trace answers back. Compliance says no.
- **Sections blur** — Risk Factors and MD&A become one wall of text. Retrieval pulls the wrong context.
- **Structure is lost** — Headers, emphasis, lists — the cues LLMs use to reason — gone.

Your RAG system is only as good as your input data. Garbage in, garbage out.

## The Solution

```python
import sec2md

pages = sec2md.parse_filing(
    "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    user_agent="Your Name <you@example.com>"
)

# 60 pages | 293 citable elements | 46,238 tokens
# Tables intact. Pages tracked. Sections detected. Ready for your pipeline.
```

`sec2md` rebuilds SEC filings as clean, semantic Markdown that LLMs can actually work with — preserving the structure, tables, and pagination that make retrieval and citation possible.

---

## Trace Every Answer Back to the Source

Most Markdown converters throw away provenance. You get text, but no way to prove *where* it came from. When your LLM says "revenue was $394B," your compliance team asks: *show me.* With a generic converter, you can't.

sec2md solves this. Every piece of content — every paragraph, table, and heading — gets a **stable, traceable element ID** that maps directly back to the original HTML. From chunk to element to source DOM node, the chain is unbroken.

```python
parser = sec2md.Parser(filing_html)
pages = parser.get_pages()
chunks = sec2md.chunk_pages(pages)

chunk = chunks[5]
print(chunk.element_ids)
# ['sec2md-p12-p0-a1b2c3d4', 'sec2md-p12-t0-e5f6a7b8', ...]

# Open the original filing in your browser — scrolls to the source, highlights in yellow
chunk.visualize(parser.html())
```

![Traceability](traceability.png)
*`chunk.visualize()` opens the original filing HTML, scrolls to the chunk's source elements, and highlights them.*

This isn't a nice-to-have — it's table stakes for production RAG on regulated documents. Every `Chunk` carries page numbers (both sequential and the original display page from the filing footer), element IDs for citation, and a direct link back to the source HTML. Every `Element` can do the same:

```python
element = chunk.elements[0]
element.visualize(parser.html())  # Highlights just this element
```

### What We Support

| Filing Type | Section Extraction | Notes |
|---|---|---|
| **10-K** | 18 items (ITEM 1–16) | Full PART/ITEM detection |
| **10-Q** | 11 items (Parts I & II) | Including financial statements |
| **8-K** | 41 items (1.01–9.01) | With exhibit parsing from 9.01 |
| **20-F** | Items 1–19, 16A–16I | Foreign private issuers |
| **DEF 14A, Exhibits** | — | Parsed as clean Markdown |

---

## Installation

```bash
pip install sec2md
```

## What You Can Do

### Pull exactly the section you need

Don't process 200 pages when you only need Risk Factors:

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

print(risk.page_range)  # (12, 28)
print(risk.tokens)       # 8,412
```

Works across filing types — 10-K, 10-Q, 8-K, and 20-F.

### Chunk for RAG with full traceability

Page-aware, token-budgeted chunks — each one carrying element IDs and page numbers you can trace back to the source:

```python
chunks = sec2md.chunk_pages(pages, chunk_size=512)

for chunk in chunks:
    print(chunk.content)             # Clean markdown text
    print(chunk.page_range)          # (12, 13)
    print(chunk.display_page_range)  # (45, 46) — as printed in the filing
    print(chunk.element_ids)         # Traceable source elements
    print(chunk.has_table)           # True — tables kept intact
```

### Keep financial tables readable

SEC tables are notoriously complex — rowspans, colspans, merged cells, currency symbols in separate columns. Some filings don't even use `<table>` tags, building tables from absolutely-positioned CSS divs instead.

sec2md handles both, and large tables are automatically split across chunks with headers preserved:

```markdown
| Product Category | Revenue (millions) |
|------------------|-------------------|
| iPhone           | $200,583          |
| Mac              | $29,357           |
| iPad             | $28,300           |
```

### Works with edgartools

Pair with [edgartools](https://github.com/dgunning/edgartools) for end-to-end filing pipelines:

```python
from edgar import Company

company = Company("AAPL")
filing = company.get_filings(form="10-K").latest()
md = sec2md.convert_to_markdown(filing.html())
```

---

## Why sec2md?

**Traceable end-to-end.** Generic Markdown converters give you text with no provenance. sec2md gives you a full citation chain — from chunk to element to source DOM node — with stable IDs, page numbers, and one-line visualization back to the original filing. When compliance asks "where did this number come from?", you have an answer.

**Purpose-built for SEC filings.** Not a generic HTML-to-Markdown converter — sec2md understands EDGAR's quirks: XBRL inline tags, PDF-to-HTML artifacts, multi-column absolute positioning, nested table wrappers, and the dozen other ways SEC HTML breaks standard parsers.

**One function call, zero configuration.** `parse_filing(html)` returns structured pages with elements, ready for chunking, section extraction, or direct use. No configuration files. No schema definitions. No training step.

---

## Documentation

Full documentation: [sec2md.readthedocs.io](https://sec2md.readthedocs.io)

- [Quickstart Guide](https://sec2md.readthedocs.io/quickstart)
- [Convert Filings](https://sec2md.readthedocs.io/usage/direct-conversion)
- [Extract Sections](https://sec2md.readthedocs.io/usage/sections)
- [Chunking for RAG](https://sec2md.readthedocs.io/usage/chunking)
- [EdgarTools Integration](https://sec2md.readthedocs.io/usage/edgartools)
- [API Reference](https://sec2md.readthedocs.io/api/convert_to_markdown)

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT © 2025
