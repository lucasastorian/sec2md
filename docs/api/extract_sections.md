# extract_sections & get_section

Extract specific sections from 10-K and 10-Q filings.

## extract_sections

Extract all sections from filing pages.

### Signature

```python
def extract_sections(
    pages: List[Page],
    filing_type: FilingType,
    debug: bool = False
) -> List[Section]
```

### Parameters

**`pages`** *(List[Page])*
: List of Page objects from `convert_to_markdown(return_pages=True)`

**`filing_type`** *("10-K" | "10-Q")*
: Type of filing to extract sections from

**`debug`** *(bool)*
: Enable debug logging
: Default: `False`

### Returns

**`List[Section]`**
: List of Section objects, each containing:
: - `part`: Part identifier (e.g., "PART I")
: - `item`: Item identifier (e.g., "ITEM 1A")
: - `item_title`: Section title (e.g., "Risk Factors")
: - `pages`: List[Page] for this section
: - `page_range`: Tuple of (start_page, end_page)
: - `markdown()`: Get section content as string

### Example

```python
import sec2md

pages = sec2md.convert_to_markdown(html, return_pages=True)
sections = sec2md.extract_sections(pages, filing_type="10-K")

for section in sections:
    print(f"{section.item}: {section.item_title}")
    print(f"  Pages {section.page_range[0]}-{section.page_range[1]}")
```

---

## get_section

Get a specific section by item enum or string.

### Signature

```python
def get_section(
    sections: List[Section],
    item: Union[Item10K, Item10Q, str],
    filing_type: FilingType = "10-K"
) -> Optional[Section]
```

### Parameters

**`sections`** *(List[Section])*
: List of sections from `extract_sections()`

**`item`** *(Item10K | Item10Q | str)*
: Section to retrieve:
: - `Item10K.RISK_FACTORS` (type-safe enum)
: - `"ITEM 1A"` (string)
: - `"1A"` (auto-prefixed with "ITEM ")

**`filing_type`** *("10-K" | "10-Q")*
: Type of filing (must match enum type)
: Default: `"10-K"`

### Returns

**`Section | None`**
: Section object if found, otherwise `None`

### Examples

#### Using Enums (Recommended)

```python
from sec2md import Item10K

sections = sec2md.extract_sections(pages, filing_type="10-K")

# Type-safe enum access
risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
business = sec2md.get_section(sections, Item10K.BUSINESS)
md_and_a = sec2md.get_section(sections, Item10K.MD_AND_A)

if risk:
    print(risk.markdown())
```

#### Using Strings

```python
# String access (less type-safe)
risk = sec2md.get_section(sections, "ITEM 1A", filing_type="10-K")
# Or shorthand
risk = sec2md.get_section(sections, "1A", filing_type="10-K")
```

## Available Enums

### Item10K

```python
from sec2md import Item10K

# Part I
Item10K.BUSINESS
Item10K.RISK_FACTORS
Item10K.PROPERTIES
Item10K.LEGAL_PROCEEDINGS

# Part II
Item10K.MD_AND_A
Item10K.MARKET_RISK
Item10K.FINANCIAL_STATEMENTS
Item10K.CONTROLS_AND_PROCEDURES

# Part III & IV
Item10K.DIRECTORS_AND_OFFICERS
Item10K.EXECUTIVE_COMPENSATION
Item10K.EXHIBITS
```

[See complete list →](../usage/sections.md#available-section-enums)

### Item10Q

```python
from sec2md import Item10Q

# Part I
Item10Q.FINANCIAL_STATEMENTS_P1
Item10Q.MD_AND_A_P1
Item10Q.MARKET_RISK_P1

# Part II
Item10Q.LEGAL_PROCEEDINGS_P2
Item10Q.RISK_FACTORS_P2
Item10Q.EXHIBITS_P2
```

Note: 10-Q enums include `_P1`/`_P2` suffixes to disambiguate duplicate item numbers.

## Section Object

```python
section = sec2md.get_section(sections, Item10K.RISK_FACTORS)

section.part          # "PART I"
section.item          # "ITEM 1A"
section.item_title    # "Risk Factors"
section.pages         # List[Page]
section.page_range    # (12, 25)
section.markdown()    # Full section as markdown string
```

## See Also

- [Section Extraction Guide](../usage/sections.md) - Complete examples
- [chunk_section](chunk.md) - Chunk sections for embeddings
