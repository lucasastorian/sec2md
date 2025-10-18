# Direct Conversion

Convert different types of SEC documents to Markdown.

## Full Filings (10-K, 10-Q)

```python
import sec2md

# Convert entire 10-K filing
md = sec2md.convert_to_markdown(
    "https://www.sec.gov/Archives/edgar/data/.../10k.htm",
    user_agent="Your Name <you@example.com>"
)
```

## Financial Statements

Financial statements are already well-structured - convert them directly:

```python
# Balance sheet, income statement, cash flow
statement_html = open("balance_sheet.html").read()
md = sec2md.convert_to_markdown(statement_html)
```

**Output preserves table structure:**
```markdown
| Assets                          | 2024      | 2023      |
|---------------------------------|-----------|-----------|
| Current assets:                 |           |           |
| Cash and cash equivalents       | $29,943   | $24,977   |
| Marketable securities           | $31,590   | $31,590   |
...
```

## Notes to Financial Statements

Notes are wrapped in outer table elements. Use `flatten_note()` to unwrap:

```python
import sec2md

# Notes need flattening first
note_html = open("revenue_note.html").read()
flattened = sec2md.flatten_note(note_html)
md = sec2md.convert_to_markdown(flattened)
```

## Press Releases (8-K Exhibits)

```python
# 8-K press releases convert directly
press_release_html = open("earnings_release.html").read()
md = sec2md.convert_to_markdown(press_release_html)
```

## Other Exhibits

Merger agreements, contracts, and other exhibits:

```python
# Exhibits (contracts, agreements, etc.)
exhibit_html = open("merger_agreement.html").read()
md = sec2md.convert_to_markdown(exhibit_html)
```

## Best Practices

**When to use `flatten_note()`:**
- ✅ Notes to financial statements
- ✅ Accounting policy disclosures
- ❌ Financial statements (already structured)
- ❌ Full filings (no outer wrapper)

**User-Agent Requirements:**

The SEC requires a user-agent for all requests:

```python
# ✅ Good
md = sec2md.convert_to_markdown(url, user_agent="John Doe john@example.com")

# ❌ Will raise ValueError
md = sec2md.convert_to_markdown(url)
```

## Next Steps

- [Extract specific sections](sections.md) - Pull just Risk Factors or MD&A
- [Work with EdgarTools](edgartools.md) - Automate filing downloads
- [Chunk for embeddings](chunking.md) - Prepare for RAG pipelines
