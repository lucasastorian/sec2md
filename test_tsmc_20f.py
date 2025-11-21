"""Test TSMC 20-F section extraction."""

import sys
sys.path.insert(0, 'src')

from sec2md import Parser
from sec2md.section_extractor import SectionExtractor
from edgar import Company, set_identity

set_identity("Lucas Astorian <lucas@intellifin.ai>")

# TSMC ticker
company = Company('TSM')
filings = company.get_filings(form='20-F')

# Get most recent 20-F
filing = next(iter(filings))
print(f"Testing filing: {filing.accession_number}")
print(f"Filing date: {filing.filing_date}")

parser = Parser(filing.html())
pages = parser.get_pages(include_elements=False)

print(f"\nTotal pages: {len(pages)}")

# Look for ITEM 1, 2, 3 etc in early pages
print("\n=== Looking for PART I items in pages 1-15 ===")
for page in pages[:15]:
    if any(pattern in page.content for pattern in ['ITEM 1', 'ITEM 2', 'ITEM 3', 'ITEM 4', 'ITEM 5']):
        print(f"\nPage {page.number}:")
        # Show first 500 chars
        print(page.content[:500])
        print("...")

print("\n=== Extracting sections with debug ===")
extractor = SectionExtractor(pages, filing_type="20-F", debug=True)
sections = extractor.get_sections()

print(f"\n\nExtracted {len(sections)} sections:")
for s in sections[:10]:  # Show first 10
    title = s.item_title[:60] if s.item_title and len(s.item_title) > 60 else (s.item_title or "")
    print(f"  {s.part}/{s.item}: {title} (pages {s.pages})")

if len(sections) > 10:
    print(f"  ... and {len(sections) - 10} more")

# Check what items we got
items_found = [s.item for s in sections]
print(f"\nItems found: {items_found}")

# Check what's missing from PART I
expected_part1 = ["ITEM 1", "ITEM 2", "ITEM 3", "ITEM 4", "ITEM 4A", "ITEM 5",
                  "ITEM 6", "ITEM 7", "ITEM 8", "ITEM 9", "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 12D"]
missing = [item for item in expected_part1 if item not in items_found]
print(f"\nMissing from PART I: {missing}")
