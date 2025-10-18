# convert_to_markdown

Convert SEC filing HTML to Markdown.

## Signature

```python
def convert_to_markdown(
    source: str | bytes,
    *,
    user_agent: str | None = None,
    return_pages: bool = False,
) -> str | List[Page]
```

## Parameters

**`source`** *(str | bytes)*
: URL or HTML string/bytes to convert

**`user_agent`** *(str | None)*
: User agent for EDGAR requests (required for `sec.gov` URLs)
: Format: `"Your Name <you@example.com>"`

**`return_pages`** *(bool)*
: If `True`, returns `List[Page]` instead of markdown string
: Default: `False`

## Returns

**`str`** (when `return_pages=False`)
: Full document as markdown string

**`List[Page]`** (when `return_pages=True`)
: List of Page objects with `.number` and `.content` attributes

## Raises

**`ValueError`**
: - If source is PDF content
: - If EDGAR URL accessed without `user_agent`

**`requests.RequestException`**
: If URL fetch fails

## Examples

### Basic Conversion

```python
import sec2md

# From URL
md = sec2md.convert_to_markdown(
    "https://www.sec.gov/Archives/edgar/data/.../10k.htm",
    user_agent="John Doe <john@example.com>"
)
```

### From HTML File

```python
with open("10k.html") as f:
    html = f.read()

md = sec2md.convert_to_markdown(html)
```

### Get Pages for Section Extraction

```python
pages = sec2md.convert_to_markdown(
    html,
    return_pages=True  # Returns List[Page]
)

# Each page has number and content
for page in pages:
    print(f"Page {page.number}: {page.content[:100]}...")
```

## Notes

- **User-Agent Requirement**: The SEC requires a user-agent header for all requests. Always provide your name and email when fetching from `sec.gov` URLs.

- **Token Usage**: Use `return_pages=True` when you need page tracking for citations or section extraction.

- **PDF Detection**: The function automatically detects and rejects PDF content with a helpful error message.

## See Also

- [extract_sections](extract_sections.md) - Extract specific sections from pages
- [chunk_pages](chunk.md) - Split pages into chunks for embeddings
