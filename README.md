# sec2md

[![PyPI](https://img.shields.io/pypi/v/sec2md.svg)](https://pypi.org/project/sec2md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-readthedocs-blue.svg)](https://sec2md.readthedocs.io)

Transform messy SEC filings into clean, structured Markdown.
**Built for AI. Optimized for retrieval. Traceable to the source.**

![Before and After Comparison](comparison.png)
*Apple 10-K: Raw SEC HTML (left) vs. sec2md output (right)*

---

## The Problem

SEC filings are the worst documents you'll ever feed to an LLM — 200 pages of nested HTML, XBRL tags, invisible elements, and tables-within-tables.

When you throw this at a standard parser:

- **Tables break** — Financial statements become garbled text. Your model hallucinates numbers.
- **Pages vanish** — Can't cite sources. Can't trace answers back. Compliance says no.
- **Sections blur** — Risk Factors and MD&A become one wall of text. Retrieval pulls the wrong context.
- **Structure is lost** — Headers, emphasis, lists — the cues LLMs use to reason — gone.

And even the converters that handle the HTML well still throw away **provenance**. You get clean text with no way to trace it back to where it came from in the original filing. For production RAG on regulated documents, that's a dealbreaker.

## The Solution

```python
import sec2md

parser = sec2md.Parser(filing_html)
pages = parser.get_pages()

# 60 pages | 293 citable elements | 46,238 tokens
# Tables intact. Pages tracked. Sections detected. Every element traceable.
```

`sec2md` rebuilds SEC filings as clean, semantic Markdown — preserving the structure, tables, and pagination that make retrieval possible. But unlike generic converters, it also preserves the **full citation chain** from every piece of output back to the source HTML.

---

## Traceability

Every paragraph, table, and heading gets a **stable element ID** that maps directly to a DOM node in the original filing HTML. From chunk to element to source — the chain is unbroken.

```python
chunks = sec2md.chunk_pages(pages, chunk_size=512)

chunk = chunks[5]
print(chunk.element_ids)
# ['sec2md-p12-p0-a1b2c3d4', 'sec2md-p12-t0-e5f6a7b8', ...]
print(chunk.page_range)          # (12, 13)
print(chunk.display_page_range)  # (45, 46) — as printed in the filing

# Open the original filing in your browser — scrolls to the source, highlights in yellow
chunk.visualize(parser.html())
```

![Traceability](examples/tracability.png)
*`chunk.visualize()` opens the original filing HTML, scrolls to the chunk's source elements, and highlights them.*

Every `Chunk` carries page numbers (both sequential and the original display page from the filing footer), element IDs for citation, and a direct link back to the source HTML. Every `Element` can do the same:

```python
element = chunk.elements[0]
element.visualize(parser.html())  # Highlights just this element
```

---

## What You Can Do

### Extract sections

Don't process 200 pages when you only need Risk Factors:

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

print(risk.page_range)  # (7, 19)
print(risk.tokens)       # 11,474
```

Works across 10-K, 10-Q, 8-K, and 20-F.

| Filing Type | Section Extraction | Notes |
|---|---|---|
| **10-K** | 18 items (ITEM 1-16) | Full PART/ITEM detection |
| **10-Q** | 11 items (Parts I & II) | Including financial statements |
| **8-K** | 41 items (1.01-9.01) | With exhibit parsing from 9.01 |
| **20-F** | Items 1-19, 16A-16I | Foreign private issuers |
| **DEF 14A, Exhibits** | -- | Parsed as clean Markdown |

### Handle complex tables

SEC tables are notoriously complex — rowspans, colspans, merged cells, currency symbols in separate columns. Some filings don't even use `<table>` tags, building tables from absolutely-positioned CSS divs instead. sec2md handles both, and large tables are automatically split across chunks with headers preserved.

### Works with edgartools

Pair with [edgartools](https://github.com/dgunning/edgartools) for end-to-end filing pipelines:

```python
from edgar import Company

company = Company("AAPL")
filing = company.get_filings(form="10-K").latest()
pages = sec2md.parse_filing(filing.html())
```

---

## Installation

```bash
pip install sec2md
```

## Getting Started

Try the [Getting Started notebook](examples/getting_started.ipynb) — parse a real 10-K, extract sections, chunk for RAG, and visualize traceability in under a minute.

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
