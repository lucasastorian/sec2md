# Page-Aware Chunking

Split markdown into semantic chunks while preserving page numbers for citation and retrieval.

## Why Chunk?

Large filings (200+ pages) exceed LLM context windows. Chunking enables:
- Embedding generation for vector search
- Page-level citation ("found on page 47")
- Section-aware retrieval
- Controlled context windows

## Basic Chunking

```python
import sec2md

pages = sec2md.parse_filing(filing_html)

# Chunk with defaults (512 tokens, 128 overlap)
chunks = sec2md.chunk_pages(pages)

for chunk in chunks:
    print(f"Pages {chunk.page_range}: {chunk.content[:100]}...")
    print(f"Tokens: {chunk.num_tokens}")
    print(f"Has table: {chunk.has_table}")
    print(f"Elements: {chunk.element_ids}")
```

## Chunk Parameters

```python
chunks = sec2md.chunk_pages(
    pages,
    chunk_size=512,          # Target size in tokens
    chunk_overlap=128,       # Overlap between chunks
    max_table_tokens=2048,   # Split tables exceeding this budget
)
```

**Token Estimation:**
- Uses [tiktoken](https://github.com/openai/tiktoken) if installed, otherwise `len(text) // 4`
- For exact counts, use your embedding provider's tokenizer
- Adjust `chunk_size` based on your model's limits

## Section-Aware Chunking

Chunk specific sections instead of entire filings:

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")
risk_section = sec2md.get_section(sections, Item10K.RISK_FACTORS)

chunks = sec2md.chunk_section(
    risk_section,
    chunk_size=512,
    chunk_overlap=128
)
```

## TextBlock Chunking

Chunk individual XBRL TextBlocks (financial statement notes):

```python
text_blocks = sec2md.merge_text_blocks(pages)

for tb in text_blocks:
    print(f"{tb.title} (pages {tb.start_page}–{tb.end_page})")
    chunks = sec2md.chunk_text_block(tb, chunk_size=512)
```

## Chunk Object

Each `Chunk` provides:

```python
chunk = chunks[0]

# Content
chunk.content          # Markdown text (no header)
chunk.embedding_text   # Content with header prepended
chunk.num_tokens       # Estimated token count
chunk.has_table        # Contains a table?

# Page tracking
chunk.page             # Primary page number
chunk.start_page       # First page in chunk
chunk.end_page         # Last page in chunk
chunk.page_range       # (start_page, end_page)
chunk.display_page_range  # Original page numbers as printed in filing

# Citation
chunk.element_ids      # List of source element IDs
chunk.elements         # Element objects in this chunk
chunk.index            # Sequential chunk index

# Serialization
chunk.to_dict()        # Full dictionary representation
chunk.set_vector(vec)  # Attach embedding vector
```

## Improving Retrieval with Headers

Add contextual metadata to chunks for better retrieval quality:

```python
from sec2md import Item10K

risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

header = f"""# Apple Inc. (AAPL - NASDAQ)
Sector: Technology | Industry: Consumer Electronics
Form 10-K | FY 2024 | Filed: 2024-11-01

## Risk Factors
"""

chunks = sec2md.chunk_section(risk, header=header)

for chunk in chunks:
    vector = embed_function(chunk.embedding_text)

    vector_db.add({
        "text": chunk.content,
        "vector": vector,
        "page": chunk.page,
        "display_page": chunk.display_page_range,
        "element_ids": chunk.element_ids,
        "item": "ITEM 1A",
        "company": "AAPL",
        "form": "10-K",
        "year": 2024
    })
```

## Table Splitting

Large tables (common in financial statements) are automatically handled:

```python
chunks = sec2md.chunk_pages(pages, max_table_tokens=2048)
```

When a table exceeds `max_table_tokens`, it is split into multiple chunks with:
- Header row repeated in each chunk
- Ellipsis rows (`| ... | ... |`) indicating continuation

## Complete RAG Example

```python
import sec2md
from sec2md import Item10K

# 1. Parse and extract
pages = sec2md.parse_filing(filing_html)
sections = sec2md.extract_sections(pages, filing_type="10-K")

# 2. Process each section
for section in sections:
    header = f"""# {company_name} ({ticker})
Form 10-K | FY {year}

## {section.item_title}
"""

    # 3. Chunk with header
    chunks = sec2md.chunk_section(section, header=header)

    # 4. Embed and store
    for chunk in chunks:
        vector = embed(chunk.embedding_text)
        vector_db.add({
            "content": chunk.content,
            "vector": vector,
            "page_range": chunk.page_range,
            "display_page_range": chunk.display_page_range,
            "element_ids": chunk.element_ids,
            "item": section.item,
            "company": ticker
        })
```

## Best Practices

**Chunk Size:**
- 512 tokens: Good for detailed retrieval
- 1024 tokens: Better for context-heavy queries
- 256 tokens: Very granular, more chunks

**Overlap:**
- 128 tokens: Standard (25% overlap with 512 chunks)
- 0 tokens: No overlap (faster, but may miss context)

**Headers:**
- Always include company, form type, section
- Add filing date for time-sensitive queries
- Keep headers consistent across your dataset

## Next Steps

- [API Reference](../api/chunk.md) - Full parameter docs
