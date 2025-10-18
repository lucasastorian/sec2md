# Section Extraction

Extract specific sections (ITEM 1, ITEM 1A, etc.) from 10-K and 10-Q filings.

## Why Extract Sections?

Instead of processing entire 200-page filings, extract just the sections you need:
- Risk Factors (ITEM 1A)
- Business Description (ITEM 1)
- MD&A (ITEM 7)
- Financial Statements (ITEM 8)

## Basic Usage

```python
import sec2md
from sec2md import Item10K

# Get pages
pages = sec2md.convert_to_markdown(filing_html, return_pages=True)

# Extract all sections
sections = sec2md.extract_sections(pages, filing_type="10-K")

# Get specific section by enum
risk_factors = sec2md.get_section(sections, Item10K.RISK_FACTORS)
business = sec2md.get_section(sections, Item10K.BUSINESS)

# Access section content
print(risk_factors.markdown())
print(f"Pages: {risk_factors.page_range}")  # (12, 25)
```

## Available Section Enums

### 10-K Sections (`Item10K`)

```python
from sec2md import Item10K

# Part I
Item10K.BUSINESS                    # ITEM 1
Item10K.RISK_FACTORS                # ITEM 1A
Item10K.UNRESOLVED_STAFF_COMMENTS   # ITEM 1B
Item10K.CYBERSECURITY               # ITEM 1C
Item10K.PROPERTIES                  # ITEM 2
Item10K.LEGAL_PROCEEDINGS           # ITEM 3
Item10K.MINE_SAFETY                 # ITEM 4

# Part II
Item10K.MARKET_FOR_STOCK            # ITEM 5
Item10K.MD_AND_A                    # ITEM 7
Item10K.MARKET_RISK                 # ITEM 7A
Item10K.FINANCIAL_STATEMENTS        # ITEM 8
Item10K.CONTROLS_AND_PROCEDURES     # ITEM 9A

# Part III & IV
Item10K.DIRECTORS_AND_OFFICERS      # ITEM 10
Item10K.EXECUTIVE_COMPENSATION      # ITEM 11
Item10K.EXHIBITS                    # ITEM 15
```

### 10-Q Sections (`Item10Q`)

```python
from sec2md import Item10Q

# Part I
Item10Q.FINANCIAL_STATEMENTS_P1         # ITEM 1 (Part I)
Item10Q.MD_AND_A_P1                     # ITEM 2 (Part I)
Item10Q.MARKET_RISK_P1                  # ITEM 3 (Part I)
Item10Q.CONTROLS_AND_PROCEDURES_P1      # ITEM 4 (Part I)

# Part II
Item10Q.LEGAL_PROCEEDINGS_P2            # ITEM 1 (Part II)
Item10Q.RISK_FACTORS_P2                 # ITEM 1A (Part II)
Item10Q.OTHER_INFORMATION_P2            # ITEM 5 (Part II)
Item10Q.EXHIBITS_P2                     # ITEM 6 (Part II)
```

Note: 10-Q has duplicate item numbers across parts, so enums include `_P1` / `_P2` suffixes.

## Section Object

Each `Section` contains:

```python
section = sec2md.get_section(sections, Item10K.RISK_FACTORS)

section.part          # "PART I"
section.item          # "ITEM 1A"
section.item_title    # "Risk Factors"
section.pages         # List[Page] objects
section.page_range    # (start, end) tuple
section.markdown()    # Get content as markdown string
```

## Working with Sections

### Iterate All Sections

```python
sections = sec2md.extract_sections(pages, filing_type="10-K")

for section in sections:
    print(f"{section.item}: {section.item_title}")
    print(f"  Pages {section.page_range[0]}-{section.page_range[1]}")
    print(f"  Length: {len(section.markdown())} chars")
```

### Extract Multiple Sections

```python
# Get several sections at once
sections_to_extract = [
    Item10K.BUSINESS,
    Item10K.RISK_FACTORS,
    Item10K.MD_AND_A
]

extracted = {}
for item in sections_to_extract:
    section = sec2md.get_section(sections, item)
    if section:
        extracted[item.name] = section.markdown()
```

### Save Sections to Files

```python
sections = sec2md.extract_sections(pages, filing_type="10-K")

for section in sections:
    if section.item:
        filename = f"{section.item.replace(' ', '_')}.md"
        with open(filename, 'w') as f:
            f.write(section.markdown())
```

## How It Works

The extractor:
1. Detects `PART I`, `PART II`, etc. headers
2. Detects `ITEM X` patterns with regex
3. Splits content by section boundaries
4. Validates against known 10-K/10-Q structures
5. Tracks page numbers for each section

Sections that span multiple pages maintain correct page order.

## Next Steps

- [Chunk sections](chunking.md) - Split sections into embeddings
- [API Reference](../api/extract_section.md) - Full parameter docs
