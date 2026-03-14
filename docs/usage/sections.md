# Section Extraction

Extract specific sections (ITEM 1, ITEM 1A, etc.) from 10-K, 10-Q, 8-K, and 20-F filings.

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

pages = sec2md.parse_filing(filing_html)

sections = sec2md.extract_sections(pages, filing_type="10-K")

risk_factors = sec2md.get_section(sections, Item10K.RISK_FACTORS)
business = sec2md.get_section(sections, Item10K.BUSINESS)

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
Item10K.SELECTED_FINANCIAL_DATA     # ITEM 6
Item10K.MD_AND_A                    # ITEM 7
Item10K.MARKET_RISK                 # ITEM 7A
Item10K.FINANCIAL_STATEMENTS        # ITEM 8
Item10K.CHANGES_IN_ACCOUNTING       # ITEM 9
Item10K.CONTROLS_AND_PROCEDURES     # ITEM 9A
Item10K.OTHER_INFORMATION           # ITEM 9B
Item10K.CYBERSECURITY_DISCLOSURES   # ITEM 9C

# Part III
Item10K.DIRECTORS_AND_OFFICERS      # ITEM 10
Item10K.EXECUTIVE_COMPENSATION      # ITEM 11
Item10K.SECURITY_OWNERSHIP          # ITEM 12
Item10K.CERTAIN_RELATIONSHIPS       # ITEM 13
Item10K.PRINCIPAL_ACCOUNTANT        # ITEM 14

# Part IV
Item10K.EXHIBITS                    # ITEM 15
Item10K.FORM_10K_SUMMARY            # ITEM 16
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
Item10Q.UNREGISTERED_SALES_P2           # ITEM 2 (Part II)
Item10Q.DEFAULTS_P2                     # ITEM 3 (Part II)
Item10Q.OTHER_INFORMATION_P2            # ITEM 5 (Part II)
Item10Q.EXHIBITS_P2                     # ITEM 6 (Part II)
```

Note: 10-Q has duplicate item numbers across parts, so enums include `_P1` / `_P2` suffixes.

### 8-K Items (`Item8K`)

```python
from sec2md import Item8K

Item8K.MATERIAL_AGREEMENT           # 1.01
Item8K.TERMINATION_OF_AGREEMENT     # 1.02
Item8K.BANKRUPTCY                   # 1.03
Item8K.MINE_SAFETY                  # 1.04
Item8K.CYBERSECURITY_INCIDENT       # 1.05
Item8K.ACQUISITION_DISPOSITION      # 2.01
Item8K.RESULTS_OF_OPERATIONS        # 2.02
Item8K.DIRECT_OBLIGATION            # 2.03
Item8K.DELISTING                    # 3.01
Item8K.DIRECTOR_OFFICER_CHANGE      # 5.02
Item8K.AMENDMENTS_TO_ARTICLES       # 5.03
Item8K.REGULATION_FD                # 7.01
Item8K.OTHER_EVENTS                 # 8.01
Item8K.FINANCIAL_STATEMENTS_EXHIBITS  # 9.01
# ... and 27 more (41 total)
```

8-K sections include automatic exhibit parsing from Item 9.01:

```python
sections = sec2md.extract_sections(pages, filing_type="8-K")

for section in sections:
    print(f"{section.item} — {section.item_title}")
    for ex in section.exhibits:
        print(f"  Exhibit {ex.exhibit_no}: {ex.description}")
```

### Filing Type Support

| Filing Type | Enum | Items |
|---|---|---|
| `"10-K"` | `Item10K` | 18 items |
| `"10-Q"` | `Item10Q` | 11 items |
| `"8-K"` | `Item8K` | 41 items |
| `"20-F"` | — | Items 1–19, 16A–16I |

## Section Object

Each `Section` contains:

```python
section = sec2md.get_section(sections, Item10K.RISK_FACTORS)

section.part          # "PART I"
section.item          # "ITEM 1A"
section.item_title    # "Risk Factors"
section.pages         # List[Page] objects
section.page_range    # (start, end) tuple
section.tokens        # Total token count
section.markdown()    # Content as markdown string
section.exhibits      # List[Exhibit] (8-K Item 9.01)
```

## Working with Sections

### Iterate All Sections

```python
sections = sec2md.extract_sections(pages, filing_type="10-K")

for section in sections:
    print(f"{section.item}: {section.item_title}")
    print(f"  Pages {section.page_range[0]}-{section.page_range[1]}")
    print(f"  Tokens: {section.tokens}")
```

### Extract Multiple Sections

```python
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

## Next Steps

- [Chunk sections](chunking.md) - Split sections into embeddings
- [API Reference](../api/extract_sections.md) - Full parameter docs
