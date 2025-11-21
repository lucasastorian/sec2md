"""Find Accounting Policies TextBlock."""

from edgar import Company, set_identity
from sec2md import Parser

# Setup
set_identity("Test User test@example.com")

# Get Apple's latest 10-K
print("Fetching Apple 10-K...")
company = Company('AAPL')
filing = company.get_filings(form="10-K").latest()
raw_html = filing.html()

print("Parsing filing...")
parser = Parser(content=raw_html)
pages = parser.get_pages(include_elements=True)

print(f"\nTotal pages: {len(pages)}")
print("\nSearching for Accounting Policies TextBlock...")

for page in pages:
    if page.text_blocks:
        for tb in page.text_blocks:
            if 'AccountingPolicies' in tb.name or 'SignificantAccounting' in tb.name:
                print(f"\n✅ Found on Page {page.number}:")
                print(f"   Name: {tb.name}")
                print(f"   Title: {tb.title}")
                print(f"   Elements: {len(tb.elements)}")
                print(f"\n   Content preview:\n   {page.content[:300]}")
                print("\n" + "="*80)

print("\nSearching for pages after Accounting Policies to see if it bleeds...")
found_accounting = False
accounting_page = None

for page in pages:
    if page.text_blocks:
        for tb in page.text_blocks:
            if 'AccountingPolicies' in tb.name or 'SignificantAccounting' in tb.name:
                found_accounting = True
                accounting_page = page.number
                break

    # Check next 10 pages after we find Accounting Policies
    if found_accounting and accounting_page and page.number > accounting_page and page.number <= accounting_page + 10:
        if page.text_blocks:
            has_accounting = any('AccountingPolicies' in tb.name or 'SignificantAccounting' in tb.name for tb in page.text_blocks)
            if has_accounting:
                print(f"\n⚠️  Page {page.number} (after page {accounting_page}) still has Accounting Policies TextBlock!")
                print(f"   Content: {page.content[:200]}")
            else:
                print(f"✅ Page {page.number}: No Accounting Policies TextBlock (has {len(page.text_blocks)} other TextBlocks)")
        else:
            print(f"✅ Page {page.number}: No TextBlocks at all")
