from __future__ import annotations

import re
from typing import List, Dict, Optional, Literal, Union, Any

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
    def __init__(self, pages: List[Any], filing_type: Optional[Literal["10-K", "10-Q", "20-F", "8-K"]] = None,
                 desired_items: Optional[set] = None, debug: bool = False):
        """Initialize SectionExtractor.

        Args:
            pages: List of Page objects
            filing_type: Type of filing ("10-K", "10-Q", "20-F", or "8-K")
            desired_items: For 8-K only: set of item numbers to extract (e.g., {"2.02", "9.01"})
            debug: Enable debug logging
        """
        from sec2md.models import Page

        # Store original Page objects to preserve elements
        self._original_pages = {p.number: p for p in pages}

        # Convert to dict format for internal processing
        self.pages = [{"page": p.number, "content": p.content} for p in pages]
        self.filing_type = filing_type
        self.structure = FILING_STRUCTURES.get(filing_type) if filing_type else None
        self.desired_items = desired_items
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

    # ========== 8-K Specific Methods ==========

    # 8-K item header regex: ITEM 1.01 / 7.01 / 9.01
    _ITEM_8K_RE = re.compile(
        rf'^\s*{LEAD_WRAP}(ITEM)\s+([1-9]\.\d{{2}}[A-Z]?)\.?\s*(?:[:.\-–—]\s*)?(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    # 8-K hard stops (SIGNATURES, EXHIBIT INDEX)
    _HARD_STOP_8K_RE = re.compile(r'^\s*(SIGNATURES|EXHIBIT\s+INDEX)\b', re.IGNORECASE | re.MULTILINE)

    # Promote inline "Item x.xx" to its own line
    _PROMOTE_ITEM_8K_RE = re.compile(r'(?<!\n)(\s)(ITEM\s+[1-9]\.\d{2}[A-Z]?\s*[.:–—-])', re.IGNORECASE)

    # Exhibits table parsing
    _PIPE_ROW_RE = re.compile(r'^\s*\|?\s*([0-9]{1,4}(?:\.[0-9A-Za-z]+)?)\s*\|\s*(.+?)\s*\|?\s*$', re.MULTILINE)
    _SPACE_ROW_RE = re.compile(r'^\s*([0-9]{1,4}(?:\.[0-9A-Za-z]+)?)\s{2,}(.+?)\s*$', re.MULTILINE)
    _HTML_ROW_RE = re.compile(
        r'<tr[^>]*>\s*<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>\s*<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>\s*</tr>',
        re.IGNORECASE | re.DOTALL
    )

    @staticmethod
    def _normalize_8k_item_code(code: str) -> str:
        """Normalize '5.2' -> '5.02', keep suffix 'A' if present."""
        code = code.upper().strip()
        m = re.match(r'^([1-9])\.(\d{1,2})([A-Z]?)$', code)
        if not m:
            return code
        major, minor, suffix = m.groups()
        minor = f"{int(minor):02d}"
        return f"{major}.{minor}{suffix}"

    def _clean_8k_text(self, text: str) -> str:
        """Clean 8-K text: remove headers/footers, normalize whitespace, promote inline items."""
        text = text.replace(NBSP, " ").replace(NARROW_NBSP, " ").replace(ZWSP, "")

        # Promote inline item headings to their own line
        text = self._PROMOTE_ITEM_8K_RE.sub(r'\n\2', text)

        # Remove Form 8-K headers/footers
        header_footer_8k = re.compile(
            r'^\s*(Form\s+8\-K|Page\s+\d+(?:\s+of\s+\d+)?|UNITED\s+STATES\s+SECURITIES\s+AND\s+EXCHANGE\s+COMMISSION)\b',
            re.IGNORECASE
        )

        lines: List[str] = []
        for ln in text.splitlines():
            t = ln.strip()
            if header_footer_8k.match(t):
                continue
            t = MD_EDGE.sub("", t)  # strip leading/trailing **/__ wrappers
            # Drop trivial table header separators like | --- | --- |
            if re.fullmatch(r'\|\s*-{3,}\s*\|\s*-{3,}\s*\|?', t):
                continue
            lines.append(t)

        # Collapse multiple blank lines into one
        out: List[str] = []
        prev_blank = False
        for ln in lines:
            blank = (ln == "")
            if blank and prev_blank:
                continue
            out.append(ln)
            prev_blank = blank

        return "\n".join(out).strip()

    def _parse_exhibits(self, block: str) -> List[Any]:
        """Parse exhibit table from 9.01 section."""
        from sec2md.models import Exhibit

        rows: List[Exhibit] = []

        # Try pipe table rows first
        for m in self._PIPE_ROW_RE.finditer(block):
            left, right = m.group(1).strip(), m.group(2).strip()
            if not re.match(r'^\d', left):
                continue  # skip headers like "EXHIBIT NO."
            if left.startswith('---') or right.startswith('---'):
                continue  # skip separators
            rows.append(Exhibit(exhibit_no=left, description=right))
        if rows:
            return rows

        # Fallback: space-aligned two columns
        for m in self._SPACE_ROW_RE.finditer(block):
            left, right = m.group(1).strip(), m.group(2).strip()
            if not re.match(r'^\d', left):
                continue
            rows.append(Exhibit(exhibit_no=left, description=right))
        if rows:
            return rows

        # Fallback: basic HTML table
        for m in self._HTML_ROW_RE.finditer(block):
            left, right = m.group(1).strip(), m.group(2).strip()
            if not re.match(r'^\d', left):
                continue
            rows.append(Exhibit(exhibit_no=left, description=right))

        return rows

    def _slice_8k_body(self, doc: str, start_after: int, next_item_start: int) -> str:
        """Slice body text from start_after up to earliest hard stop or next_item_start."""
        mstop = self._HARD_STOP_8K_RE.search(doc, pos=start_after, endpos=next_item_start)
        end = mstop.start() if mstop else next_item_start
        return doc[start_after:end].strip()

    def _get_8k_sections(self) -> List[Any]:
        """Extract 8-K sections (items only, no PART divisions)."""
        from sec2md.models import Section, Page, ITEM_8K_TITLES

        # Concatenate all pages into one doc
        full_content = "\n\n".join(p["content"] for p in self.pages)
        doc = self._clean_8k_text(full_content)

        if not doc:
            self._log("DEBUG: No content after cleaning")
            return []

        # Find all item headers
        headers: List[Dict] = []
        for m in self._ITEM_8K_RE.finditer(doc):
            code = self._normalize_8k_item_code(m.group(2))
            title_inline = (m.group(3) or "").strip()
            # Clean markdown artifacts from title
            title_inline = MD_EDGE.sub("", title_inline)
            title = title_inline if title_inline else ITEM_8K_TITLES.get(code)
            headers.append({"start": m.start(), "end": m.end(), "no": code, "title": title})
            self._log(f"DEBUG: Found ITEM {code} at position {m.start()}")

        if not headers:
            self._log("DEBUG: No item headers found")
            return []

        self._log(f"DEBUG: Total headers found: {len(headers)}")

        # Extract sections
        results: List[Section] = []
        for i, h in enumerate(headers):
            code = h["no"]
            next_start = headers[i + 1]["start"] if i + 1 < len(headers) else len(doc)
            body = self._slice_8k_body(doc, h["end"], next_start)

            # Filter by desired_items if provided
            if self.desired_items and code not in self.desired_items:
                self._log(f"DEBUG: Skipping ITEM {code} (not in desired_items)")
                continue

            # For 9.01, parse exhibits
            exhibits = []
            if code.startswith("9.01"):
                md = re.search(r'^\s*\(?d\)?\s*Exhibits\b.*$', body, re.IGNORECASE | re.MULTILINE)
                ex_block = body[md.end():].strip() if md else body
                exhibits = self._parse_exhibits(ex_block)
                self._log(f"DEBUG: Found {len(exhibits)} exhibits in 9.01")

            # Map back to Page objects (approximate page boundaries from original content)
            # Since 8-K sections can span pages, we need to find which pages contain this content
            section_pages = self._map_8k_content_to_pages(body)

            # Create Section with exhibits (now part of the model)
            section = Section(
                part=None,  # 8-K has no PART divisions
                item=f"ITEM {code}",
                item_title=h["title"],
                pages=section_pages,
                exhibits=exhibits if exhibits else None
            )

            results.append(section)
            self._log(f"DEBUG: Extracted ITEM {code} with {len(section_pages)} pages")

        self._log(f"DEBUG: Total sections extracted: {len(results)}")
        return results

    def _map_8k_content_to_pages(self, section_content: str) -> List[Any]:
        """Map extracted section content back to Page objects."""
        # Find which original pages contain this section content
        # This is heuristic-based: match by content overlap
        matched_pages = []
        section_preview = section_content[:500]  # Use first 500 chars for matching

        for page_dict in self.pages:
            page_num = page_dict["page"]
            page_content_cleaned = self._clean_8k_text(page_dict["content"])

            # Check if this page contains part of the section (using cleaned content for matching)
            if section_preview in page_content_cleaned or page_content_cleaned in section_content:
                # Use the original Page object directly to preserve elements/text_blocks
                matched_pages.append(self._original_pages[page_num])

        return matched_pages

    # ========== End 8-K Methods ==========

    def get_sections(self) -> List[Any]:
        """Get sections from the filing.

        Routes to appropriate handler based on filing_type:
        - 8-K: Uses _get_8k_sections() (flat item structure)
        - 10-K/10-Q/20-F: Uses _get_standard_sections() (PART + ITEM structure)
        """
        if self.filing_type == "8-K":
            return self._get_8k_sections()
        else:
            return self._get_standard_sections()

    def _get_standard_sections(self) -> List[Any]:
        """Extract 10-K/10-Q/20-F sections (PART + ITEM structure)."""
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

        # Convert to Section objects with Page objects (preserving elements)
        from sec2md.models import Section, Page

        section_objects = []
        for section_data in sections:
            # Build Page objects for this section, preserving elements from originals
            section_pages = []
            for page_dict in section_data["pages"]:
                page_num = page_dict["page"]
                original_page = self._original_pages.get(page_num)

                # Filter text_blocks to only include ones relevant to this section's content
                filtered_text_blocks = None
                if original_page and original_page.text_blocks:
                    section_content = page_dict["content"]
                    filtered_text_blocks = []
                    for tb in original_page.text_blocks:
                        # Include TextBlock if:
                        # 1. Its title appears in section content, OR
                        # 2. Any of its element content appears in section (for short titles)
                        title_match = tb.title and tb.title in section_content
                        content_match = any(
                            # Check if element content (or significant portion) is in section
                            elem.content[:200] in section_content or section_content in elem.content
                            for elem in tb.elements
                        )
                        if title_match or content_match:
                            filtered_text_blocks.append(tb)
                    filtered_text_blocks = filtered_text_blocks if filtered_text_blocks else None

                section_pages.append(
                    Page(
                        number=page_num,
                        content=page_dict["content"],
                        elements=original_page.elements if original_page else None,
                        text_blocks=filtered_text_blocks
                    )
                )

            section_objects.append(
                Section(
                    part=section_data["part"],
                    item=section_data["item"],
                    item_title=section_data["item_title"],
                    pages=section_pages
                )
            )

        return section_objects

    def get_section(self, part: str, item: Optional[str] = None):
        """Get a specific section by part and item.

        Args:
            part: Part name (e.g., "PART I")
            item: Optional item name (e.g., "ITEM 1A")

        Returns:
            Section object if found, None otherwise
        """
        from sec2md.models import Section

        part_normalized = self._normalize_section(part)
        item_normalized = self._normalize_section(item) if item else None
        sections = self.get_sections()

        for section in sections:
            if section.part == part_normalized:
                if item_normalized is None or section.item == item_normalized:
                    return section
        return None
