# Page-Aware Chunking

Split markdown into semantic chunks while preserving page numbers for citation and retrieval.

## Why Chunk?

Large filings (200+ pages) exceed LLM context windows. Chunking enables:
- ✅ Embedding generation for vector search
- ✅ Page-level citation ("found on page 47")
- ✅ Section-aware retrieval
- ✅ Controlled context windows

## Basic Chunking

```python
import sec2md

# Get pages
pages = sec2md.convert_to_markdown(filing_html, return_pages=True)

# Chunk with defaults (512 tokens, 128 overlap)
chunks = sec2md.chunk_pages(pages)

for chunk in chunks:
    print(f"Page {chunk.page}: {chunk.content[:100]}...")
    print(f"Estimated tokens: {chunk.num_tokens}")
    print(f"Has table: {chunk.has_table}")
```

## Chunk Parameters

```python
chunks = sec2md.chunk_pages(
    pages,
    chunk_size=512,      # Target size in tokens
    chunk_overlap=128    # Overlap between chunks
)
```

**Token Estimation:**
- Uses `len(text) // 4` heuristic
- Good approximation for most text
- For exact counts, use your embedding provider's tokenizer

## Section-Aware Chunking

Chunk specific sections instead of entire filings:

```python
from sec2md import Item10K

# Extract section
sections = sec2md.extract_sections(pages, filing_type="10-K")
risk_section = sec2md.get_section(sections, Item10K.RISK_FACTORS)

# Chunk just this section
chunks = sec2md.chunk_section(
    risk_section,
    chunk_size=512,
    chunk_overlap=128
)
```

## Chunk Object

Each `MarkdownChunk` provides:

```python
chunk = chunks[0]

chunk.page           # Page number
chunk.content        # Markdown text (no header)
chunk.embedding_text # Text for embedding (includes header if provided)
chunk.num_tokens     # Estimated token count
chunk.has_table      # Boolean - contains table?
chunk.blocks         # Internal block structure
```

## Improving Retrieval with Headers

Add contextual metadata to chunks for **significantly better** retrieval quality:

```python
from sec2md import Item10K

# Extract section
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

# Build rich header with metadata
header = f"""# Apple Inc. (AAPL - NASDAQ)
Sector: Technology | Industry: Consumer Electronics
Form 10-K | FY 2024 | Filed: 2024-11-01

## Risk Factors
"""

# Chunk with header
chunks = sec2md.chunk_section(risk, header=header)

# Embed and store
for chunk in chunks:
    # embedding_text includes the header
    vector = embed_function(chunk.embedding_text)

    # Store with metadata
    vector_db.add({
        "text": chunk.content,      # Original text (no header)
        "vector": vector,            # Embedding with header context
        "page": chunk.page,
        "item": "ITEM 1A",
        "company": "AAPL",
        "form": "10-K",
        "year": 2024
    })
```

### Why Headers Improve Retrieval

**Without header:**
```
"The Company faces intense competition in the smartphone market..."
```

**With header:**
```
# Apple Inc. (AAPL - NASDAQ)
Form 10-K | FY 2024

## Risk Factors

...

The Company faces intense competition in the smartphone market...
```

The embedding now encodes:
- Company name and ticker
- Document type (10-K)
- Section (Risk Factors)
- Filing year

User queries like *"What are Apple's risks in 2024?"* will retrieve this chunk with much higher accuracy.

## Complete RAG Example

```python
import sec2md
from sec2md import Item10K

# 1. Convert and extract
pages = sec2md.convert_to_markdown(filing_html, return_pages=True)
sections = sec2md.extract_sections(pages, filing_type="10-K")

# 2. Process each section
for section in sections:
    # Build section-specific header
    header = f"""# {company_name} ({ticker} - {exchange})
Sector: {sector} | Industry: {industry}
Form 10-K | FY {year} | Filed: {filing_date}

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
            "page": chunk.page,
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

- [Concepts: LLM Readiness](../concepts/llm-readiness.md) - Why structured chunks matter
- [API Reference](../api/chunk.md) - Full parameter docs
