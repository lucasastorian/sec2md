# Working with EdgarTools

`sec2md` integrates seamlessly with [edgartools](https://github.com/dgunning/edgartools) for automated filing downloads and parsing.

## Setup

```bash
pip install sec2md edgartools
```

## Basic Integration

```python
from edgar import Company, set_identity
import sec2md

# Set SEC-compliant identity
set_identity("Your Name <you@example.com>")

# Get company and filing
company = Company("AAPL")
filing = company.get_filings(form="10-K").latest()

# Convert to markdown
md = sec2md.convert_to_markdown(filing.html())
```

## Financial Statements

```python
# Get specific statement
statements = filing.reports.get_by_category("Statements")
statement = statements.get_by_short_name("CONSOLIDATED STATEMENTS OF OPERATIONS")

# Convert directly (no flattening needed)
md = sec2md.convert_to_markdown(statement.content)
```

## Notes to Financial Statements

Notes require flattening before conversion:

```python
# Get note
notes = filing.reports.get_by_category("Notes")
note = notes.get_by_short_name("Revenue")

# Flatten, then convert
flattened = sec2md.flatten_note(note.content)
md = sec2md.convert_to_markdown(flattened)
```

## Press Releases (8-K)

```python
# Get latest 8-K
filing = company.get_filings(form="8-K").latest()

# First attachment is usually the press release
exhibit = filing.attachments[0]
md = sec2md.convert_to_markdown(exhibit.download())
```

## Exhibits

```python
# Get specific exhibit by number
filing = company.get_filings(form="8-K").latest()
exhibit = filing.get_exhibit("2.1")  # Merger agreement

md = sec2md.convert_to_markdown(exhibit.download())
```

## Complete Example: Build a Filing Dataset

```python
from edgar import Company, set_identity
import sec2md

set_identity("Your Name <you@example.com>")

def process_company_filings(ticker: str, years: int = 3):
    """Download and convert recent filings to markdown"""
    company = Company(ticker)
    filings = company.get_filings(form="10-K").head(years)

    results = []
    for filing in filings:
        # Get pages for section extraction
        pages = sec2md.convert_to_markdown(
            filing.html(),
            return_pages=True
        )

        # Extract sections
        sections = sec2md.extract_sections(pages, filing_type="10-K")

        results.append({
            "ticker": ticker,
            "filing_date": filing.filing_date,
            "sections": sections
        })

    return results

# Process Apple's last 3 10-Ks
data = process_company_filings("AAPL", years=3)
```

## Why Use EdgarTools?

EdgarTools handles:
- ✅ Filing discovery and filtering
- ✅ Automatic downloads
- ✅ XBRL parsing
- ✅ Attachment extraction

`sec2md` handles:
- ✅ HTML → clean Markdown conversion
- ✅ Table preservation
- ✅ Section extraction
- ✅ Page-aware chunking

Together they create a complete filing processing pipeline.

## Next Steps

- [Extract sections](sections.md) - Pull specific ITEMs
- [Chunk for RAG](chunking.md) - Prepare for embeddings
