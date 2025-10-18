# chunk_pages & chunk_section

Split markdown into page-aware chunks for embeddings.

## chunk_pages

Chunk pages into overlapping markdown chunks.

### Signature

```python
def chunk_pages(
    pages: List[Page],
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[MarkdownChunk]
```

### Parameters

**`pages`** *(List[Page])*
: List of Page objects from `convert_to_markdown(return_pages=True)`

**`chunk_size`** *(int)*
: Target chunk size in tokens (estimated as chars/4)
: Default: `512`

**`chunk_overlap`** *(int)*
: Overlap between chunks in tokens
: Default: `128`

**`header`** *(str | None)*
: Optional header to prepend to each chunk's `embedding_text`
: Not included in `content`, only in `embedding_text`
: Default: `None`

### Returns

**`List[MarkdownChunk]`**
: List of chunk objects with page tracking

### Example

```python
import sec2md

pages = sec2md.convert_to_markdown(html, return_pages=True)
chunks = sec2md.chunk_pages(pages, chunk_size=512, chunk_overlap=128)

for chunk in chunks:
    print(f"Page {chunk.page}: {chunk.content[:100]}...")
    print(f"Tokens: {chunk.num_tokens}")
```

---

## chunk_section

Chunk a filing section.

### Signature

```python
def chunk_section(
    section: Section,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    header: Optional[str] = None
) -> List[MarkdownChunk]
```

### Parameters

**`section`** *(Section)*
: Section object from `get_section()`

**`chunk_size`** *(int)*
: Target chunk size in tokens
: Default: `512`

**`chunk_overlap`** *(int)*
: Overlap between chunks in tokens
: Default: `128`

**`header`** *(str | None)*
: Optional header for embedding context
: Default: `None`

### Returns

**`List[MarkdownChunk]`**
: List of chunk objects

### Example

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

chunks = sec2md.chunk_section(risk, chunk_size=512)
```

---

## MarkdownChunk Object

Each chunk provides:

```python
chunk = chunks[0]

chunk.page           # int - Page number
chunk.content        # str - Markdown content (no header)
chunk.embedding_text # str - Content with header prepended
chunk.num_tokens     # int - Estimated token count
chunk.has_table      # bool - Contains table?
chunk.blocks         # List - Internal block structure
chunk.pages          # List[dict] - Page data for this chunk
```

## Using Headers for Better Retrieval

Headers improve embedding quality by adding contextual metadata:

```python
from sec2md import Item10K

# Extract section
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)

# Build rich header
header = f"""# Apple Inc. (AAPL - NASDAQ)
Sector: Technology | Industry: Consumer Electronics
Form 10-K | FY 2024 | Filed: 2024-11-01

## Risk Factors
"""

# Chunk with header
chunks = sec2md.chunk_section(risk, header=header)

# Embed and store
for chunk in chunks:
    # embedding_text includes header
    vector = embed(chunk.embedding_text)

    # Store with original content (no header)
    db.add({
        "text": chunk.content,
        "vector": vector,
        "page": chunk.page,
        "item": "ITEM 1A"
    })
```

**Key Points:**

- `chunk.content` = original text (no header)
- `chunk.embedding_text` = header + `...` + content
- Embeddings capture metadata context
- Retrieved content shows only filing text

## Token Estimation

Chunks use `len(text) // 4` as a token approximation:

- Good enough for most use cases
- For exact counts, use your embedding provider's tokenizer
- Adjust `chunk_size` based on your model's limits

## Chunk Size Recommendations

| Size  | Use Case                           |
|-------|------------------------------------|
| 256   | Very granular, more chunks         |
| 512   | Standard for detailed retrieval    |
| 1024  | Better for context-heavy queries   |
| 2048  | Large context windows              |

**Overlap:**
- 128 tokens (25% of 512): Standard
- 0 tokens: No overlap, faster processing
- 256 tokens (50%): High overlap for better coverage

## See Also

- [Chunking Guide](../usage/chunking.md) - Complete examples and best practices
- [extract_sections](extract_sections.md) - Extract sections before chunking
