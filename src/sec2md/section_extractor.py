from __future__ import annotations

import re
from typing import List, Dict, Optional, Literal

LEAD_WRAP = r'(?:\*\*|__)?\s*(?:</?[^>]+>\s*)*'

PART_PATTERN = re.compile(
    rf'^\s*{LEAD_WRAP}(PART\s+[IVXLC]+)\b(?:\s*$|\s+)',
    re.IGNORECASE | re.MULTILINE
)
ITEM_PATTERN = re.compile(
    rf'^\s*{LEAD_WRAP}(ITEM)\s+(\d{{1,2}}[A-Z]?)\.?\s*(?:[:.\-–—]\s*)?(.*)',
    re.IGNORECASE | re.MULTILINE
)

HEADER_FOOTER_RE = re.compile(
    r'^\s*(?:[A-Z][A-Za-z0-9 .,&\-]+)?\s*\|\s*\d{4}\s+Form\s+10-[KQ]\s*\|\s*\d+\s*$'
)
PAGE_NUM_RE = re.compile(r'^\s*Page\s+\d+\s*(?:of\s+\d+)?\s*$|^\s*\d+\s*$', re.IGNORECASE)
MD_EDGE = re.compile(r'^\s*(?:\*\*|__)\s*|\s*(?:\*\*|__)\s*$')

NBSP, NARROW_NBSP, ZWSP = '\u00A0', '\u202F', '\u200B'

DOT_LEAD_RE = re.compile(r'^.*\.{3,}\s*\d{1,4}\s*$', re.M)  # "... 123"
ITEM_ROWS_RE = re.compile(r'^\s*ITEM\s+\d{1,2}[A-Z]?\.?\b', re.I | re.M)

FILING_STRUCTURES = {
    "10-K": {
        "PART I": ["ITEM 1", "ITEM 1A", "ITEM 1B", "ITEM 1C", "ITEM 2", "ITEM 3", "ITEM 4"],
        "PART II": ["ITEM 5", "ITEM 6", "ITEM 7", "ITEM 7A", "ITEM 8", "ITEM 9", "ITEM 9A", "ITEM 9B", "ITEM 9C"],
        "PART III": ["ITEM 10", "ITEM 11", "ITEM 12", "ITEM 13", "ITEM 14"],
        "PART IV": ["ITEM 15", "ITEM 16"]
    },
    "10-Q": {
        "PART I": ["ITEM 1", "ITEM 2", "ITEM 3", "ITEM 4"],
        "PART II": ["ITEM 1", "ITEM 1A", "ITEM 2", "ITEM 3", "ITEM 4", "ITEM 5", "ITEM 6"]
    },
    "20-F": {
        "PART I": [
            "ITEM 1", "ITEM 2", "ITEM 3", "ITEM 4", "ITEM 5", "ITEM 6",
            "ITEM 7", "ITEM 8", "ITEM 9", "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 12D"
        ],
        "PART II": [
            "ITEM 13", "ITEM 14", "ITEM 15",
            # include all 16X variants explicitly so validation stays strict
            "ITEM 16", "ITEM 16A", "ITEM 16B", "ITEM 16C", "ITEM 16D", "ITEM 16E", "ITEM 16F", "ITEM 16G", "ITEM 16H",
            "ITEM 16I"
        ],
        "PART III": ["ITEM 17", "ITEM 18", "ITEM 19"]
    }
}


class SectionExtractor:
    def __init__(self, pages: List[Dict], filing_type: Optional[Literal["10-K", "10-Q", "20-F"]] = None, debug: bool = False):
        self.pages = pages
        self.filing_type = filing_type
        self.structure = FILING_STRUCTURES.get(filing_type) if filing_type else None
        self.debug = debug

        self._toc_locked = False

    def _log(self, msg: str):
        if self.debug:
            print(msg)

    @staticmethod
    def _normalize_section_key(part: Optional[str], item_num: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        part_key = re.sub(r'\s+', ' ', part.upper().strip()) if part else None
        item_key = f"ITEM {item_num.upper()}" if item_num else None
        return part_key, item_key

    @staticmethod
    def _normalize_section(text: str) -> str:
        return re.sub(r'\s+', ' ', text.upper().strip())

    def _clean_lines(self, content: str) -> List[str]:
        content = content.replace(NBSP, ' ').replace(NARROW_NBSP, ' ').replace(ZWSP, '')
        lines = [ln.rstrip() for ln in content.split('\n')]
        out = []
        for ln in lines:
            if HEADER_FOOTER_RE.match(ln) or PAGE_NUM_RE.match(ln):
                continue
            ln = MD_EDGE.sub('', ln)
            out.append(ln)
        return out

    def _infer_part_for_item(self, filing_type: str, item_key: str) -> Optional[str]:
        m = re.match(r'ITEM\s+(\d{1,2})', item_key)
        if not m:
            return None
        num = int(m.group(1))
        if filing_type == "10-K":
            if 1 <= num <= 4:
                return "PART I"
            elif 5 <= num <= 9:
                return "PART II"
            elif 10 <= num <= 14:
                return "PART III"
            elif 15 <= num <= 16:
                return "PART IV"
        elif filing_type == "10-Q":
            if 1 <= num <= 4:
                return "PART I"
            else:
                return "PART II"
        return None

    @staticmethod
    def _clean_item_title(title: str) -> str:
        title = re.sub(r'^\s*[:.\-–—]\s*', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def _is_toc(self, content: str, page_num: int = 1) -> bool:
        # Simple rule: within first 5 pages, if we see multiple matches, treat as TOC.
        # “Multiple” = ≥3 ITEM rows OR ≥3 dotted-leader lines.
        if self._toc_locked or page_num > 5:
            return False

        item_hits = len(ITEM_ROWS_RE.findall(content))
        leader_hits = len(DOT_LEAD_RE.findall(content))

        return (item_hits >= 3) or (leader_hits >= 3)
    def get_sections(self) -> List[Dict]:
        sections = []
        current_part = None
        current_item = None
        current_item_title = None
        current_pages: List[Dict] = []

        def flush_section():
            nonlocal sections, current_part, current_item, current_item_title, current_pages
            if current_pages:
                sections.append({
                    "part": current_part,
                    "item": current_item,
                    "item_title": current_item_title,
                    "page_start": current_pages[0]["page"],
                    "pages": current_pages
                })
                current_pages = []

        for page_dict in self.pages:
            page_num = page_dict["page"]
            content = page_dict["content"]

            if self._is_toc(content, page_num):
                self._log(f"DEBUG: Page {page_num} detected as TOC, skipping")
                continue

            lines = self._clean_lines(content)
            joined = "\n".join(lines)

            if not joined.strip():
                self._log(f"DEBUG: Page {page_num} is empty after cleaning")
                continue

            part_m = None
            item_m = None
            first_idx = None
            first_kind = None

            for m in PART_PATTERN.finditer(joined):
                part_m = m
                first_idx = m.start()
                first_kind = 'part'
                self._log(f"DEBUG: Page {page_num} found PART at position {first_idx}: {m.group(1)}")
                break

            for m in ITEM_PATTERN.finditer(joined):
                if first_idx is None or m.start() < first_idx:
                    item_m = m
                    first_idx = m.start()
                    first_kind = 'item'
                    self._log(f"DEBUG: Page {page_num} found ITEM at position {first_idx}: ITEM {m.group(2)}")
                break

            if first_kind is None:
                self._log(f"DEBUG: Page {page_num} - no header found. In section: {current_part or current_item}")
                if current_part or current_item:
                    if joined.strip():
                        current_pages.append({"page": page_num, "content": joined})
                continue

            before = joined[:first_idx].strip()
            after = joined[first_idx:].strip()

            if (current_part or current_item) and before:
                current_pages.append({"page": page_num, "content": before})

            flush_section()

            if first_kind == 'part' and part_m:
                part_text = part_m.group(1)
                current_part, _ = self._normalize_section_key(part_text, None)
                current_item = None
                current_item_title = None
            elif first_kind == 'item' and item_m:
                item_num = item_m.group(2)
                title = (item_m.group(3) or "").strip()
                current_item_title = self._clean_item_title(title) if title else None
                if current_part is None and self.filing_type:
                    inferred = self._infer_part_for_item(self.filing_type, f"ITEM {item_num.upper()}")
                    if inferred:
                        current_part = inferred
                        self._log(f"DEBUG: Inferred {inferred} at detection time for ITEM {item_num}")
                _, current_item = self._normalize_section_key(current_part, item_num)

            if after:
                current_pages.append({"page": page_num, "content": after})

                if first_kind == 'part' and part_m:
                    item_after = None
                    for m in ITEM_PATTERN.finditer(after):
                        item_after = m
                        break
                    if item_after:
                        start = item_after.start()
                        current_pages[-1]["content"] = after[start:]
                        item_num = item_after.group(2)
                        title = (item_after.group(3) or "").strip()
                        current_item_title = self._clean_item_title(title) if title else None
                        _, current_item = self._normalize_section_key(current_part, item_num)
                        self._log(f"DEBUG: Page {page_num} - promoted PART to ITEM {item_num} (intra-page)")
                        after = current_pages[-1]["content"]

                tail = after
                while True:
                    next_kind, next_idx, next_part_m, next_item_m = None, None, None, None

                    for m in PART_PATTERN.finditer(tail):
                        if m.start() > 0:
                            next_kind, next_idx, next_part_m = 'part', m.start(), m
                            break
                    for m in ITEM_PATTERN.finditer(tail):
                        if m.start() > 0 and (next_idx is None or m.start() < next_idx):
                            next_kind, next_idx, next_item_m = 'item', m.start(), m

                    if next_idx is None:
                        break

                    before_seg = tail[:next_idx].strip()
                    after_seg = tail[next_idx:].strip()

                    if before_seg:
                        current_pages[-1]["content"] = before_seg
                    flush_section()

                    if next_kind == 'part' and next_part_m:
                        current_part, _ = self._normalize_section_key(next_part_m.group(1), None)
                        current_item = None
                        current_item_title = None
                        self._log(f"DEBUG: Page {page_num} - intra-page PART transition to {current_part}")
                    elif next_kind == 'item' and next_item_m:
                        item_num = next_item_m.group(2)
                        title = (next_item_m.group(3) or "").strip()
                        current_item_title = self._clean_item_title(title) if title else None
                        if current_part is None and self.filing_type:
                            inferred = self._infer_part_for_item(self.filing_type, f"ITEM {item_num.upper()}")
                            if inferred:
                                current_part = inferred
                                self._log(f"DEBUG: Inferred {inferred} at detection time for ITEM {item_num}")
                        _, current_item = self._normalize_section_key(current_part, item_num)
                        self._log(f"DEBUG: Page {page_num} - intra-page ITEM transition to {current_item}")

                    current_pages.append({"page": page_num, "content": after_seg})
                    tail = after_seg

        flush_section()

        self._log(f"DEBUG: Total sections before validation: {len(sections)}")
        for s in sections:
            self._log(f"  - Part: {s['part']}, Item: {s['item']}, Pages: {len(s['pages'])}, Start: {s['page_start']}")

        def _section_text_len(s):
            return sum(len(p["content"].strip()) for p in s["pages"])

        sections = [s for s in sections if s["item"] is not None or _section_text_len(s) > 80]
        self._log(f"DEBUG: Sections after dropping empty PART stubs: {len(sections)}")

        if self.structure and sections:
            self._log(f"DEBUG: Validating against structure: {self.filing_type}")
            fixed = []
            for s in sections:
                part = s["part"]
                item = s["item"]

                if part is None and item and self.filing_type:
                    inferred = self._infer_part_for_item(self.filing_type, item)
                    if inferred:
                        self._log(f"DEBUG: Inferred {inferred} from {item}")
                        s = {**s, "part": inferred}
                        part = inferred

                if (part in self.structure) and (item is None or item in self.structure.get(part, [])):
                    fixed.append(s)
                else:
                    self._log(f"DEBUG: Dropped section - Part: {part}, Item: {item}")

            sections = fixed
            self._log(f"DEBUG: Sections after validation: {len(sections)}")

        return sections

    def get_section(self, part: str, item: Optional[str] = None) -> Optional[Dict]:
        part_normalized = self._normalize_section(part)
        item_normalized = self._normalize_section(item) if item else None
        sections = self.get_sections()

        for section in sections:
            if section["part"] == part_normalized:
                if item_normalized is None or section["item"] == item_normalized:
                    return section
        return None
