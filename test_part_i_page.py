"""Test if PART I is being preserved in parsing."""

import sys
sys.path.insert(0, 'src')

from sec2md import Parser
from edgar import Company, set_identity

set_identity("Lucas Astorian <lucas@intellifin.ai>")

company = Company('TSM')
filings = company.get_filings(form='20-F')
filing = next(iter(filings))

parser = Parser(filing.html())
pages = parser.get_pages(include_elements=False)

# Page 7 should have "PART I"
page7 = pages[6]  # 0-indexed

print("=== Page 7 Content ===")
print(page7.content[:1000])
print("\n...")

# Check if "PART I" is in the content
if "PART I" in page7.content:
    print("\n✓ 'PART I' found in page 7")
    # Find where it appears
    idx = page7.content.find("PART I")
    print(f"Position: {idx}")
    print(f"Context: {repr(page7.content[max(0, idx-50):idx+50])}")
else:
    print("\n✗ 'PART I' NOT found in page 7")

# Check if PART pattern appears anywhere
import re
part_pattern = re.compile(r'PART\s+[IVXLC]+', re.IGNORECASE)
matches = list(part_pattern.finditer(page7.content))
print(f"\nPART pattern matches: {len(matches)}")
for m in matches[:5]:
    print(f"  Position {m.start()}: {repr(m.group(0))}")
