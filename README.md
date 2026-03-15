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

pages = sec2md.parse_filing(
    "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    user_agent="Your Name <you@example.com>"
)

# 60 pages | 293 citable elements | 46,238 tokens
# Tables intact. Pages tracked. Sections detected. Every element traceable.
```

`sec2md` rebuilds SEC filings as clean, semantic Markdown — preserving the structure, tables, and pagination that make retrieval possible. But unlike generic converters, it also preserves the **full citation chain** from every piece of output back to the source HTML.

---

## Supported Filings

sec2md works with any SEC filing served as HTML. For filings with standardized structure, it also extracts individual sections automatically:

| Filing Type | Description | Section Extraction |
|---|---|---|
| **10-K** | Annual report | 18 items (ITEM 1–16), full PART/ITEM detection |
| **10-Q** | Quarterly report | 11 items (Parts I & II) |
| **8-K** | Current report (material events) | 41 items (1.01–9.01), exhibit parsing |
| **20-F** | Foreign private issuer annual report | Items 1–19, 16A–16I |
| **SC 13D** | Beneficial ownership (activist) | 7 items (Items 1–7) |
| **SC 13G** | Beneficial ownership (passive) | 10 items (Items 1–10) |
| **S-1, S-3, S-4, F-1** | Registration statements | Parsed as clean Markdown |
| **424B** | Prospectuses | Parsed as clean Markdown |
| **6-K** | Foreign private issuer current report | Parsed as clean Markdown |
| **DEF 14A, DEFA14A** | Proxy materials | Parsed as clean Markdown |
| **40-F** | Canadian cross-border annual report | Parsed as clean Markdown |
| **N-CSR** | Fund/ETF shareholder reports | Parsed as clean Markdown |
| **SC TO-T** | Tender offer statements | Parsed as clean Markdown |
| **Exhibits, Attachments** | Any HTML exhibit or attachment | Parsed as clean Markdown |

## Section-Aware Parsing

A 10-K is modular — Business, Risk Factors, MD&A, Financial Statements. sec2md detects PART and ITEM boundaries automatically, so you can pull exactly the section you need instead of processing 200 pages:

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

print(risk.page_range)  # (7, 19)
print(risk.tokens)       # 11,474
print(risk.markdown()[:200])
```

## Chunking for RAG

Page-aware, token-budgeted chunks — each one carrying page numbers, element IDs, and display pages from the filing footer:

```python
chunks = sec2md.chunk_pages(pages, chunk_size=512)

for chunk in chunks:
    print(chunk.content)             # Clean markdown text
    print(chunk.page_range)          # (12, 13)
    print(chunk.display_page_range)  # (45, 46) — as printed in the filing
    print(chunk.element_ids)         # Traceable source elements
    print(chunk.has_table)           # True — tables kept intact
```

You can also chunk individual sections or XBRL TextBlocks. Large tables are automatically split across chunks with headers preserved.

## Complex Table Handling

SEC tables are notoriously complex — rowspans, colspans, merged cells, currency symbols in separate columns. Some filings don't even use `<table>` tags, building tables from absolutely-positioned CSS divs instead.

sec2md handles both:

```markdown
| Product Category | Revenue (millions) |
|------------------|-------------------|
| iPhone           | $200,583          |
| Mac              | $29,357           |
| iPad             | $28,300           |
```

## Ready for Multimodal

SEC filings aren't just text — they're full of charts, performance graphs, and segment breakdowns that never make it into your pipeline. Most parsers silently drop every `<img>` tag. Your model never sees the revenue trend chart that would have answered the question.

sec2md extracts images as first-class elements — same page tracking, same element IDs, same citation chain as every paragraph and table:

```python
chunks = sec2md.chunk_pages(pages)

for chunk in chunks:
    if chunk.has_image:
        print(chunk.images)       # Image elements with full traceability
        print(chunk.page_range)   # Where it appeared in the filing

# Self-contained HTML — no broken image links
pages = sec2md.parse_filing(url, user_agent="...", embed_images=True)
```

Feed chunks with images to a vision model. Feed the rest to text. Every image stays traceable back to the source filing — same as everything else.

## Traceability

This is the feature most Markdown converters don't have. Every paragraph, table, and heading gets a **stable element ID** that maps directly to a DOM node in the original filing HTML. From chunk to element to source — the chain is unbroken.

```python
parser = sec2md.Parser(filing_html)
pages = parser.get_pages()
chunks = sec2md.chunk_pages(pages)

# See exactly where a chunk comes from in the original filing
chunk = chunks[5]
chunk.visualize(parser.html())

# Or drill down to a single element
chunk.elements[0].visualize(parser.html())
```

![Traceability](examples/tracability.png)
*`element.visualize()` opens the original filing HTML, scrolls to the source element, and highlights it.*

When your LLM says "revenue was $394B" and compliance asks *show me* — you can point to the exact location in the filing. Not the chunk. Not the Markdown. The source.

---

## Works with edgartools

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
