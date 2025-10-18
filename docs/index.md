# sec2md

**Convert SEC EDGAR filings to clean, LLM-ready Markdown.**

## What is sec2md?

`sec2md` transforms messy SEC HTML filings into structured Markdown designed for AI systems. Unlike generic HTML-to-text converters, it preserves tables, tracks pages, detects section boundaries, and outputs clean text optimized for embeddings and retrieval.

| Feature                 | Description                                               |
| ----------------------- | --------------------------------------------------------- |
| 🧭 **Page-aware**       | Preserves original pagination for citation traceability  |
| 🗂️ **Section-aware**   | Detects ITEM boundaries in 10-K/10-Q filings              |
| 📊 **Table-preserving** | Converts HTML tables to clean Markdown pipe syntax        |
| 🪶 **LLM-ready**        | Outputs chunk-safe Markdown for RAG pipelines             |
| 🔗 **Universal**        | Works with filings, exhibits, notes, and press releases   |

## Installation

```bash
pip install sec2md
```

## Quick Example

```python
import sec2md

# Convert any SEC filing to markdown
md = sec2md.convert_to_markdown(
    "https://www.sec.gov/Archives/edgar/data/.../10k.htm",
    user_agent="YourName you@example.com"
)

print(md)  # Clean, structured markdown
```

**Output:**
```markdown
ITEM 1. Business

Apple Inc. designs, manufactures, and markets smartphones, personal computers,
tablets, wearables, and accessories worldwide...

| Product Category | Revenue (millions) |
|------------------|-------------------|
| iPhone           | $200,583          |
| Mac              | $29,357           |
...
```

## What's Next?

- **[Quickstart →](quickstart.md)** - Get up and running in 3 minutes
- **[Convert Filings →](usage/direct-conversion.md)** - Handle 10-Ks, exhibits, press releases
- **[Extract Sections →](usage/sections.md)** - Pull specific ITEM sections (Risk Factors, MD&A, etc.)
- **[Chunking for RAG →](usage/chunking.md)** - Split filings into page-aware chunks for embeddings

## Why Markdown?

SEC filings contain XBRL tags, inline CSS, absolute positioning, and nested tables. Standard HTML parsers produce garbage. `sec2md` rebuilds the document as semantic Markdown that LLMs can actually parse - preserving structure, tables, and metadata for retrieval.

## License

MIT © 2025
