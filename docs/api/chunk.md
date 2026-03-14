# Chunking API

Split markdown into page-aware chunks for embeddings.

## chunk_pages

Chunk pages into overlapping chunks with element tracking.

### Signature

```python
def chunk_pages(
    pages: List[Page],
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    max_table_tokens: int = 2048,
    header: Optional[str] = None
) -> List[Chunk]
```

### Parameters

**`pages`** *(List[Page])*
: List of Page objects from `parse_filing()` or `convert_to_markdown(return_pages=True)`

**`chunk_size`** *(int)*
: Target chunk size in tokens
: Default: `512`

**`chunk_overlap`** *(int)*
: Overlap between chunks in tokens
: Default: `128`

**`max_table_tokens`** *(int)*
: Tables exceeding this token budget are split with repeated headers
: Default: `2048`

**`header`** *(str | None)*
: Optional header prepended to each chunk's `embedding_text`
: Not included in `content`, only in `embedding_text`
: Default: `None`

### Returns

**`List[Chunk]`**
: List of chunk objects with page tracking and element references

### Example

```python
import sec2md

pages = sec2md.parse_filing(html)
chunks = sec2md.chunk_pages(pages, chunk_size=512, chunk_overlap=128)

for chunk in chunks:
    print(f"Pages {chunk.page_range}: {chunk.content[:100]}...")
    print(f"Tokens: {chunk.num_tokens}")
```

---

## chunk_section

Chunk a single filing section.

### Signature

```python
def chunk_section(
    section: Section,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    max_table_tokens: int = 2048,
    header: Optional[str] = None
) -> List[Chunk]
```

### Parameters

**`section`** *(Section)*
: Section object from `get_section()`

**`chunk_size`** *(int)*
: Target chunk size in tokens. Default: `512`

**`chunk_overlap`** *(int)*
: Overlap between chunks in tokens. Default: `128`

**`max_table_tokens`** *(int)*
: Split tables exceeding this budget. Default: `2048`

**`header`** *(str | None)*
: Optional header for embedding context. Default: `None`

### Returns

**`List[Chunk]`**

---

## merge_text_blocks

Merge multi-page XBRL TextBlocks into single objects.

### Signature

```python
def merge_text_blocks(pages: List[Page]) -> List[TextBlock]
```

### Example

```python
text_blocks = sec2md.merge_text_blocks(pages)
for tb in text_blocks:
    print(f"{tb.title} (pages {tb.start_page}–{tb.end_page})")
```

---

## chunk_text_block

Chunk an individual XBRL TextBlock.

### Signature

```python
def chunk_text_block(
    text_block: TextBlock,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    max_table_tokens: int = 2048,
    header: Optional[str] = None
) -> List[Chunk]
```

---

## Chunk Object

Each chunk provides:

```python
chunk = chunks[0]

# Content
chunk.content              # str — Markdown content (no header)
chunk.embedding_text       # str — Content with header prepended
chunk.num_tokens           # int — Estimated token count
chunk.has_table            # bool — Contains a table?

# Page tracking
chunk.page                 # int — Primary page number
chunk.start_page           # int — First page
chunk.end_page             # int — Last page
chunk.page_range           # tuple — (start_page, end_page)
chunk.display_page_range   # Optional[tuple] — Original page numbers from filing footer

# Citation
chunk.element_ids          # List[str] — Source element IDs
chunk.elements             # List — Element objects
chunk.index                # int — Sequential chunk index

# Serialization
chunk.to_dict()            # dict — Full serialization
chunk.set_vector(vec)      # Attach embedding vector
```

## Token Estimation

Token counts use [tiktoken](https://github.com/openai/tiktoken) if installed (`cl100k_base` encoding), otherwise `len(text) // 4`. For exact counts with your specific model, use your embedding provider's tokenizer.

## See Also

- [Chunking Guide](../usage/chunking.md) - Examples and best practices
- [extract_sections](extract_sections.md) - Extract sections before chunking
