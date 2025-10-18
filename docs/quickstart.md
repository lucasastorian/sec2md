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
    "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
    user_agent="Your Name <you@example.com>"
)

# From HTML file
with open("10k.html") as f:
    html = f.read()

md = sec2md.convert_to_markdown(html)
print(md)
```

## CLI Usage

```bash
# Convert from URL
sec2md https://www.sec.gov/.../10k.htm --user-agent "you@example.com" --out filing.md

# Pipe to other tools
sec2md filing.html | grep "risk factors"
```

## What You Get

Clean Markdown with:
- ✅ Preserved tables (as Markdown pipes)
- ✅ Stripped XBRL tags
- ✅ Detected ITEM headers
- ✅ Maintained document structure

## Next Steps

**Want more control?**

- [Extract specific sections](usage/sections.md) - Pull just "Risk Factors" or "MD&A"
- [Work with EdgarTools](usage/edgartools.md) - Integrate with filing downloads
- [Chunk for embeddings](usage/chunking.md) - Split into page-aware chunks

**Need to understand how it works?**

- [Parsing philosophy](concepts/parsing-philosophy.md) - Why SEC HTML is special
- [API Reference](api/convert_to_markdown.md) - Full parameter docs
