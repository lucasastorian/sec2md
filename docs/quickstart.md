# Quickstart

Get started with `sec2md` in under 3 minutes.

## Installation

```bash
pip install sec2md
```

## Basic Conversion

Convert any SEC filing HTML to Markdown:

```python
import sec2md

# From URL (requires SEC-compliant user-agent)
md = sec2md.convert_to_markdown(
    "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    user_agent="Your Name <you@example.com>"
)

# From HTML file
with open("10k.html") as f:
    html = f.read()

md = sec2md.convert_to_markdown(html)
print(md)
```

## Structured Parsing

For RAG pipelines, use `parse_filing` to get pages with citable elements:

```python
pages = sec2md.parse_filing(html)

for page in pages:
    print(f"Page {page.number}: {page.tokens} tokens, {len(page.elements)} elements")
```

## What You Get

Clean Markdown with:
- Preserved tables (as Markdown pipes)
- Stripped XBRL tags and inline styles
- Detected ITEM/PART headers
- Citable semantic elements with stable IDs
- Original page numbers from filing footers

## Next Steps

**Want more control?**

- [Extract specific sections](usage/sections.md) - Pull just "Risk Factors" or "MD&A"
- [Work with EdgarTools](usage/edgartools.md) - Integrate with filing downloads
- [Chunk for embeddings](usage/chunking.md) - Split into page-aware chunks

**Full API docs:**

- [API Reference](api/convert_to_markdown.md) - All function signatures and parameters
