"""Pages to sections: PART and ITEM headers for 10-K, 10-Q and 20-F; items for 8-K and Schedules 13D/13G."""
from __future__ import annotations

import re
from typing import List, Literal, Optional, Tuple

from sec2md.models import Exhibit, Page, Section, ITEM_8K_TITLES, ITEM_13D_TITLES, ITEM_13G_TITLES

LEAD_WRAP = r'(?:\*\*|__)?\s*(?:</?[^>]+>\s*)*'

PART_PATTERN = re.compile(
    rf'^\s*{LEAD_WRAP}(PART\s+[IVXLC]+)\.?(?:\*\*|__)?(?:\s*$|\s+)',
    re.IGNORECASE | re.MULTILINE
)
ITEM_PATTERN = re.compile(
    rf'^\s*{LEAD_WRAP}(ITEM)\s+(\d{{1,2}}[A-Z]?)\.?[ \t]*(?:[:.\-–—][ \t]*)?(.*)',
    re.IGNORECASE | re.MULTILINE
)
ITEM_8K_PATTERN = re.compile(
    rf'^\s*{LEAD_WRAP}(ITEM)\s+([1-9]\.\d{{2}}[A-Z]?)\.?[ \t]*(?:[:.\-–—][ \t]*)?(.*)$',
    re.IGNORECASE | re.MULTILINE
)

HEADER_FOOTER_RE = re.compile(
    r'^\s*(?:[A-Z][A-Za-z0-9 .,&\-]+)?\s*\|\s*\d{4}\s+Form\s+10-[KQ]\s*\|\s*\d+\s*$'
)
PAGE_NUM_RE = re.compile(r'^\s*Page\s+\d+\s*(?:of\s+\d+)?\s*$|^\s*\d+\s*$', re.IGNORECASE)
MD_EDGE = re.compile(r'^\s*(?:\*\*|__)\s*|\s*(?:\*\*|__)\s*$')

NBSP, NARROW_NBSP, ZWSP = ' ', ' ', '​'

DOT_LEAD_RE = re.compile(r'^.*\.{3,}\s*\d{1,4}\s*$', re.M)  # "... 123"
ITEM_ROWS_RE = re.compile(r'^\s*ITEM\s+\d{1,2}[A-Z]?\.?\b', re.I | re.M)
TABLE_ITEM_RE = re.compile(r'\|\s*ITEM\s+\d{1,2}[A-Z]?\.?\s*\|', re.I)  # | ITEM 1A. | Risk Factors | 12 |
ITEM_BREADCRUMB_TITLE_RE = re.compile(
    r'^[,\s]*(\d{1,2}[A-Z]?)(\s*,\s*\d{1,2}[A-Z]?)*\s*$',
    re.IGNORECASE
)
SIGNATURE_RE = re.compile(r'^\s*(?:\*\*|__)?\s*SIGNATURE', re.IGNORECASE | re.MULTILINE)
EXHIBITS_HEADER_RE = re.compile(r'^\s*\(?d\)?\s*Exhibits\b.*$', re.IGNORECASE | re.MULTILINE)
EXHIBIT_ROW_RES = [  # exhibit-number | description, as a pipe table, spaced columns, or raw HTML rows
    re.compile(r'^\s*\|?\s*([0-9]{1,4}(?:\.[0-9A-Za-z]+)?)\s*\|\s*(.+?)\s*\|?\s*$', re.MULTILINE),
    re.compile(r'^\s*([0-9]{1,4}(?:\.[0-9A-Za-z]+)?)\s{2,}(.+?)\s*$', re.MULTILINE),
    re.compile(r'<tr[^>]*>\s*<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>\s*<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>\s*</tr>',
               re.IGNORECASE | re.DOTALL),
]

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
            "ITEM 1", "ITEM 2", "ITEM 3", "ITEM 4", "ITEM 4A", "ITEM 5",
            # Some 20-F filings include items 6-12 in PART I without explicit PART II header
            "ITEM 6", "ITEM 7", "ITEM 8", "ITEM 9", "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 12D"
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


def _slice(page: Page, content: str) -> Page:
    """Part of a page: its own content, with the page's number, elements, text blocks and printed number."""
    return Page(number=page.number, content=content, elements=page.elements,
                text_blocks=page.text_blocks, display_page=page.display_page)


def _line_at(text: str, m: re.Match) -> str:
    """The whole line a match is on."""
    start = text.rfind('\n', 0, m.start()) + 1
    end = text.find('\n', m.end())
    return text[start:end if end != -1 else len(text)].strip()


def _part_key(text: str) -> str:
    return re.sub(r'\s+', ' ', text.upper().strip())


def _clean_item_title(title: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^\s*[:.\-–—]\s*', '', title)).strip()


def _is_item_title(title: str) -> bool:
    """A real header's title, not a breadcrumb's ('ITEM 2, 3, 4' repeated at a page top)."""
    return bool(title) and not ITEM_BREADCRUMB_TITLE_RE.match(title)


class SectionExtractor:
    def __init__(self, pages: List[Page],
                 filing_type: Optional[Literal["10-K", "10-Q", "20-F", "8-K", "SC 13D", "SC 13G"]] = None,
                 desired_items: Optional[set] = None, debug: bool = False):
        """Extract sections from SEC filings."""
        self.pages = pages
        self.filing_type = filing_type
        self.structure = FILING_STRUCTURES.get(filing_type) if filing_type else None
        self.desired_items = desired_items
        self.debug = debug

    def _log(self, msg: str):
        if self.debug:
            print(msg)

    def get_sections(self) -> List[Section]:
        """Get sections from the filing."""
        if self.filing_type in ("8-K", "SC 13D", "SC 13G"):
            return self._get_item_sections()
        return self._get_standard_sections()

    def get_section(self, part: str, item: Optional[str] = None) -> Optional[Section]:
        """Get a specific section by part and item."""
        part_normalized = _part_key(part)
        item_normalized = _part_key(item) if item else None
        for section in self.get_sections():
            if section.part == part_normalized and (item_normalized is None or section.item == item_normalized):
                return section
        return None

    # -- 10-K, 10-Q, 20-F -------------------------------------------------------------------------

    @staticmethod
    def _clean_lines(content: str) -> List[str]:
        """Lines without running headers/footers and page numbers, emphasis markers stripped."""
        content = content.replace(NBSP, ' ').replace(NARROW_NBSP, ' ').replace(ZWSP, '')
        lines = [ln.rstrip() for ln in content.split('\n')]
        return [MD_EDGE.sub('', ln) for ln in lines if not (HEADER_FOOTER_RE.match(ln) or PAGE_NUM_RE.match(ln))]

    @staticmethod
    def _infer_part_for_item(filing_type: str, item_key: str) -> Optional[str]:
        """The PART a 10-K item belongs to."""
        m = re.match(r'ITEM\s+(\d{1,2})', item_key)
        if not m or filing_type != "10-K":
            return None
        num = int(m.group(1))
        for part, (lo, hi) in (("PART I", (1, 4)), ("PART II", (5, 9)), ("PART III", (10, 14)), ("PART IV", (15, 16))):
            if lo <= num <= hi:
                return part
        return None

    @staticmethod
    def _is_toc(content: str, page_num: int = 1) -> bool:
        """A table of contents page (only looked for in the first five pages)."""
        if page_num > 5:
            return False
        if len(ITEM_ROWS_RE.findall(content)) >= 3 or len(DOT_LEAD_RE.findall(content)) >= 3:
            return True
        table_item_hits = len(TABLE_ITEM_RE.findall(content))
        return table_item_hits >= 3 or (
            table_item_hits >= 2 and re.search(r'TABLE\s+OF\s+CONTENTS', content, re.IGNORECASE) is not None)

    def _get_standard_sections(self) -> List[Section]:
        """10-K/10-Q/20-F: a section per PART and ITEM header, split inside pages."""
        sections: List[Section] = []
        part = item = title = None
        pages: List[Page] = []

        def flush():
            nonlocal pages
            if pages:
                sections.append(Section(part=part, item=item, item_title=title, pages=pages))
                pages = []

        def open_item(m: re.Match) -> None:
            nonlocal part, item, title
            raw_title = (m.group(3) or "").strip()
            title = _clean_item_title(raw_title) if raw_title else None
            if part is None and self.filing_type:
                part = self._infer_part_for_item(self.filing_type, f"ITEM {m.group(2).upper()}") or part
            item = f"ITEM {m.group(2).upper()}"

        for page in self.pages:
            if self._is_toc(page.content, page.number):
                self._log(f"DEBUG: Page {page.number} detected as TOC, skipping")
                continue
            joined = "\n".join(self._clean_lines(page.content))
            if not joined.strip():
                continue

            # The page's first header: a PART, or an ITEM before it (not an inline "Part II, Item 7"
            # reference, not a breadcrumb)
            part_m = next(PART_PATTERN.finditer(joined), None)
            first_idx = part_m.start() if part_m else None
            item_m = None
            for m in ITEM_PATTERN.finditer(joined):
                if first_idx is not None and m.start() >= first_idx:
                    break
                if re.search(r'\bPart\s+[IVXLC]+', joined[max(0, m.start() - 30):m.start()], re.IGNORECASE):
                    continue
                if not _is_item_title((m.group(3) or "").strip()):
                    continue
                item_m, first_idx = m, m.start()
                break

            if first_idx is None:
                if (part or item) and joined.strip():
                    pages.append(_slice(page, joined))
                continue

            before, after = joined[:first_idx].strip(), joined[first_idx:].strip()
            if (part or item) and before:
                pages.append(_slice(page, before))
            flush()
            if item_m:
                open_item(item_m)
            else:
                part, item, title = _part_key(part_m.group(1)), None, None

            if not after:
                continue
            pages.append(_slice(page, after))

            if not item_m:
                # A PART header with its first ITEM on the same page: the section starts at the ITEM
                first_item = next((m for m in ITEM_PATTERN.finditer(after)
                                   if _is_item_title((m.group(3) or "").strip())), None)
                if first_item:
                    after = after[first_item.start():]
                    pages[-1] = _slice(page, after)
                    raw_title = (first_item.group(3) or "").strip()
                    title = _clean_item_title(raw_title) if raw_title else None
                    item = f"ITEM {first_item.group(2).upper()}"

            # Further headers on the same page
            tail = after
            while True:
                next_part = next((m for m in PART_PATTERN.finditer(tail) if m.start() > 0), None)
                next_idx = next_part.start() if next_part else None
                next_item = None
                for m in ITEM_PATTERN.finditer(tail):
                    if m.start() > 0 and (next_idx is None or m.start() < next_idx) \
                            and _is_item_title((m.group(3) or "").strip()):
                        next_item, next_idx = m, m.start()
                        break
                if next_idx is None:
                    break
                before_seg, after_seg = tail[:next_idx].strip(), tail[next_idx:].strip()
                if before_seg:
                    pages[-1] = _slice(page, before_seg)
                flush()
                if next_item:
                    open_item(next_item)
                else:
                    part, item, title = _part_key(next_part.group(1)), None, None
                pages.append(_slice(page, after_seg))
                tail = after_seg

        flush()

        # Drop the near-empty stubs of PART headers
        sections = [s for s in sections if s.item is not None or sum(len(p.content.strip()) for p in s.pages) > 80]

        if self.structure and sections:
            valid = []
            for s in sections:
                inferred = self._infer_part_for_item(self.filing_type, s.item) if s.item else None
                if inferred and inferred != s.part:
                    s = Section(part=inferred, item=s.item, item_title=s.item_title, pages=s.pages)
                if s.part in self.structure and (s.item is None or s.item in self.structure.get(s.part, [])):
                    valid.append(s)
                else:
                    self._log(f"DEBUG: Dropped section - Part: {s.part}, Item: {s.item}")
            sections = valid

        self._log(f"DEBUG: Total sections: {len(sections)}")
        return sections

    # -- 8-K, Schedules 13D and 13G ---------------------------------------------------------------

    @staticmethod
    def _normalize_8k_item_code(code: str) -> str:
        """Normalize '5.2' -> '5.02', keep suffix 'A' if present."""
        code = code.upper().strip()
        m = re.match(r'^([1-9])\.(\d{1,2})([A-Z]?)$', code)
        if not m:
            return code
        major, minor, suffix = m.groups()
        return f"{major}.{int(minor):02d}{suffix}"

    @staticmethod
    def _is_8k_boilerplate_page(page_content: str, page_num: int) -> bool:
        """Cover, table of contents and signature pages."""
        if page_num == 1 or re.search(r'TABLE OF CONTENTS', page_content, re.IGNORECASE):
            return True
        if len(re.findall(r'ITEM\s+[1-9]\.\d{2}.*?\|\s*\d+\s*\|', page_content, re.IGNORECASE)) >= 2:
            return True
        return bool(re.search(r'\*\*SIGNATURES\*\*', page_content)
                    and re.search(r'Pursuant to the requirements', page_content, re.IGNORECASE))

    @staticmethod
    def _parse_exhibits(block: str) -> List[Exhibit]:
        """The exhibit table of an Item 9.01: number | description rows."""
        for pattern in EXHIBIT_ROW_RES:
            rows = []
            for m in pattern.finditer(block):
                left, right = m.group(1).strip(), m.group(2).strip()
                if not re.match(r'^\d', left) or (pattern is EXHIBIT_ROW_RES[0] and right.startswith('---')):
                    continue
                rows.append(Exhibit(exhibit_no=left, description=right))
            if rows:
                return rows
        return []

    def _find_item_header(self, content: str, current_item: Optional[str]) -> Optional[Tuple[re.Match, str]]:
        """The first item header in the content and its item code. Table rows are not headers; in a
        schedule, an item outside the form or a sub-item ('Item 1(a)') of the current item is content."""
        if self.filing_type == "8-K":
            for m in ITEM_8K_PATTERN.finditer(content):
                if '|' not in _line_at(content, m):
                    return m, self._normalize_8k_item_code(m.group(2))
            return None
        valid_items = {str(i) for i in range(1, 11 if self.filing_type == "SC 13G" else 8)}
        for m in ITEM_PATTERN.finditer(content):
            code = m.group(2).upper()
            if '|' in _line_at(content, m) or code not in valid_items:
                continue
            if re.match(r'^\([a-z]\)', MD_EDGE.sub("", (m.group(3) or "").strip())) and current_item == f"ITEM {code}":
                continue
            return m, code
        return None

    def _get_item_sections(self) -> List[Section]:
        """8-K, SC 13D, SC 13G: a section per item header, split inside pages. 8-K cover, contents and
        signature pages are skipped; a schedule ends at its signature."""
        is_8k = self.filing_type == "8-K"
        titles = ITEM_8K_TITLES if is_8k else ITEM_13G_TITLES if self.filing_type == "SC 13G" else ITEM_13D_TITLES
        sections: List[Section] = []
        item = title = None
        pages: List[Page] = []

        def flush():
            nonlocal pages
            if pages and item:
                exhibits = None
                if item.startswith("ITEM 9.01"):
                    content = "\n".join(p.content for p in pages)
                    header = EXHIBITS_HEADER_RE.search(content)
                    exhibits = self._parse_exhibits(content[header.end():].strip() if header else content) or None
                sections.append(Section(part=None, item=item, item_title=title, pages=pages, exhibits=exhibits))
                pages = []

        for page in self.pages:
            content = page.content
            last_page = False
            if is_8k:
                if self._is_8k_boilerplate_page(content, page.number):
                    self._log(f"DEBUG: Page {page.number} is boilerplate, skipping")
                    continue
            elif signature := SIGNATURE_RE.search(content):
                content, last_page = content[:signature.start()].strip(), True
                if not content:
                    break

            while content:
                header = self._find_item_header(content, item)
                if header is None:
                    if item and content.strip():
                        pages.append(_slice(page, content))
                    break
                m, code = header
                before, content = content[:m.start()].strip(), content[m.end():].strip()
                if item and before:
                    pages.append(_slice(page, before))
                flush()
                item, title = f"ITEM {code}", MD_EDGE.sub("", (m.group(3) or "").strip()) or titles.get(code)
                if self.desired_items and code not in self.desired_items:
                    item = title = None

            if last_page:
                break

        flush()
        self._log(f"DEBUG: Total sections: {len(sections)}")
        return sections
