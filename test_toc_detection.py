"""Test TOC detection on page 2."""

import sys
sys.path.insert(0, 'src')

from sec2md import Parser
from sec2md.section_extractor import SectionExtractor, DOT_LEAD_RE, ITEM_ROWS_RE

# Use your filing details
from edgar import Company, set_identity

set_identity("Lucas Astorian <lucas@intellifin.ai>")

company = Company('TSM')
filings = list(company.get_filings(form='20-F'))

# Try the most recent one
filing = filings[0]
print(f"Testing filing: {filing.accession_number}")

parser = Parser(filing.html())
pages = parser.get_pages(include_elements=False)

print(f"\nTotal pages: {len(pages)}")

# Check page 2
page2 = pages[1]  # 0-indexed
print(f"\n=== Page 2 Content (first 1000 chars) ===")
print(page2.content[:1000])

# Test TOC detection logic
item_hits = len(ITEM_ROWS_RE.findall(page2.content))
leader_hits = len(DOT_LEAD_RE.findall(page2.content))

print(f"\n=== TOC Detection on Page 2 ===")
print(f"ITEM pattern hits: {item_hits}")
print(f"Leader dots pattern hits: {leader_hits}")
print(f"Should detect as TOC: {(item_hits >= 3) or (leader_hits >= 3)}")

# Show what ITEM_ROWS_RE is matching
print(f"\n=== ITEM matches found ===")
item_matches = list(ITEM_ROWS_RE.finditer(page2.content))[:10]
for i, match in enumerate(item_matches):
    print(f"{i+1}. Position {match.start()}: {repr(match.group(0)[:60])}")

# Show what DOT_LEAD_RE is matching
print(f"\n=== Dot leader matches found ===")
dot_matches = list(DOT_LEAD_RE.finditer(page2.content))[:10]
for i, match in enumerate(dot_matches):
    print(f"{i+1}. Position {match.start()}: {repr(match.group(0)[:60])}")

# Check table-based TOC detection
import re
table_item_pattern = re.compile(r'\|\s*ITEM\s+\d{1,2}[A-Z]?\.?\s*\|', re.IGNORECASE)
table_hits = len(table_item_pattern.findall(page2.content))
print(f"\n=== Table-based TOC detection ===")
print(f"Table ITEM pattern hits: {table_hits}")
print(f"Has 'TABLE OF CONTENTS': {bool(re.search(r'TABLE\s+OF\s+CONTENTS', page2.content, re.IGNORECASE))}")
print(f"Should detect as table TOC: {table_hits >= 3}")

# Now test the actual extractor
print(f"\n=== Running extractor with debug ===")
extractor = SectionExtractor(pages, filing_type="20-F", debug=True)
sections = extractor.get_sections()

print(f"\n=== Results ===")
print(f"Total sections extracted: {len(sections)}")
items = [s.item for s in sections]
print(f"Items: {items}")

missing_part1 = [f"ITEM {i}" for i in [1, 2, 3, 4, "4A", 5, 6, 7, 8, 9, 10, 11, 12, "12D"] if f"ITEM {i}" not in items]
print(f"Missing PART I items: {missing_part1}")
