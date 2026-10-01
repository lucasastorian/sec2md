"""Filing HTML to markdown pages: one walk over the DOM, a new page at each CSS page break."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from bs4 import BeautifulSoup
from bs4.element import (Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Script,
                         Stylesheet, Tag, TemplateString)

from sec2md.absolute_table_parser import AbsolutelyPositionedTableParser
from sec2md.element_builder import build_elements_for_pages, augment_html_with_ids, _HIGHLIGHT_SCRIPT
from sec2md.models import Page
from sec2md.table_parser import TableParser
from sec2md.utils import median, clean_text, css_px, iter_tags

logger = logging.getLogger(__name__)

BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "br", "hr", "ul", "ol", "li"}
BOLD_TAGS = {"b", "strong"}
ITALIC_TAGS = {"i", "em"}
NOT_CONTENT = (Comment, Declaration, Doctype, ProcessingInstruction)
NOT_TEXT = (Script, Stylesheet, TemplateString)  # the strings of <script>, <style>, <template>

_css_decl = re.compile(r"^[a-zA-Z\-]+\s*:\s*[^;]+;\s*$")
ITEM_HEADER_CELL_RE = re.compile(r"^\s*Item\s+([0-9IVX]+)\.\s*$", re.I)
PART_HEADER_CELL_RE = re.compile(r"^\s*Part\s+([IVX]+)\s*$", re.I)
_ABSOLUTE = re.compile(r"(?:^|[;{])position:absolute")
_LEFT_PX = re.compile(r"(?<![\w-])left:\s*(\d+(?:\.\d+)?)px")
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CLASS_SELECTOR = re.compile(r"\.([\w-]+)")
_PAGE_NUMBER_PATTERNS = [re.compile(p, re.I) for p in (r"\bPage\s+(\d{1,4})\b", r"\b(\d{1,4})\s*\|", r"\|\s*(\d{1,4})\b")]
_PART_BREADCRUMB = re.compile(r"^(?:\*\*|__)?\s*PART\s+[IVXLC]+\s*(?:\*\*|__)?$", re.I)
# e.g. "ITEM 2", "ITEM 2, 3, 4", "ITEM 9, 9A"
_ITEM_BREADCRUMB = re.compile(r"^(?:\*\*|__)?\s*ITEM\s+\d{1,2}[A-Z]?(?:\s*,\s*\d{1,2}[A-Z]?)*\s*(?:\*\*|__)?$", re.I)


def _style(el: Tag) -> str:
    """The inline style lowercased, spaces removed: the form the layout tests below read."""
    return (el.get("style") or "").lower().replace(" ", "")


def _is_absolute(style: str) -> bool:
    # Not a CSS custom property such as '--position:absolute' (2026 print-layout S-1s).
    return _ABSOLUTE.search(style) is not None


def _breaks_before(style: str) -> bool:
    return "page-break-before:always" in style or "break-before:page" in style or "break-before:always" in style


def _breaks_after(style: str) -> bool:
    return "page-break-after:always" in style or "break-after:page" in style or "break-after:always" in style


def _top_px(el: Tag) -> Optional[float]:
    """Y position in px from top: (or bottom:, counted from 10000px)."""
    style = el.get("style", "")
    top = css_px(style, "top")
    if top is not None:
        return top
    bottom = css_px(style, "bottom")
    return None if bottom is None else 10000.0 - bottom


def _plausible_page_number(num: int, min_val: int = 1) -> bool:
    return min_val <= num <= 9999 and not (1900 <= num <= 2100)


@dataclass
class TextBlockInfo:
    """The XBRL TextBlock (financial statement note) the walk is inside."""
    name: str
    title: Optional[str] = None


class Parser:
    """Filing HTML to markdown pages, each split into citable elements traced back to the HTML."""

    def __init__(self, content: str):
        self.soup = BeautifulSoup(content, "lxml")
        # Comments are strings to bs4 and were rendered as page text; filing agents
        # hide markers in them ('Field: Page; Sequence: 4', base64 'Field: Set; ...').
        # smooth() re-joins the text a comment split ('F-<!-- -->1' -> 'F-1').
        for node in [s for s in self.soup.descendants if isinstance(s, NOT_CONTENT)]:
            node.extract()
        self.soup.smooth()
        self.include_images = True
        self.pages: Dict[int, List[str]] = defaultdict(list)
        self.page_segments: Dict[int, List[Tuple[str, Optional[Tag], Optional[TextBlockInfo]]]] = defaultdict(list)
        self.current_text_block: Optional[TextBlockInfo] = None
        self.continuation_map: Dict[str, TextBlockInfo] = {}
        self.footer_page_numbers: Dict[int, int] = {}
        self._classes_break_before: frozenset = frozenset()
        self._classes_break_after: frozenset = frozenset()

    # -- XBRL text blocks ---------------------------------------------------------------------

    @staticmethod
    def _is_text_block_tag(el: Tag) -> bool:
        if not isinstance(el, Tag) or el.name not in ("ix:nonnumeric", "nonnumeric"):
            return False
        name = el.get("name", "")
        return "TextBlock" in name and (name.startswith("us-gaap:") or name.startswith("cyd:"))

    @staticmethod
    def _find_text_block_tag_in_children(el: Tag) -> Optional[Tag]:
        """The element itself, or the first TextBlock among its children and grandchildren."""
        if Parser._is_text_block_tag(el):
            return el
        for child in el.children:
            if isinstance(child, Tag):
                if Parser._is_text_block_tag(child):
                    return child
                for grandchild in child.children:
                    if Parser._is_text_block_tag(grandchild):
                        return grandchild
        return None

    @staticmethod
    def _extract_text_block_info(el: Tag) -> Optional[TextBlockInfo]:
        name = el.get("name", "")
        if not name or "TextBlock" not in name:
            return None
        tag_text = el.get_text(strip=True) or ""
        if tag_text and len(tag_text) < 200:
            title = tag_text
        else:
            name_part = name.split(":")[-1].replace("TextBlock", "")
            title = re.sub(r"\s+", " ", re.sub(r"([A-Z])", r" \1", name_part).strip())
        return TextBlockInfo(name=name, title=title)

    def _restore_text_block(self, started: bool, has_continuation: bool,
                            ends_block: bool, previous: Optional[TextBlockInfo]) -> None:
        if started and not has_continuation:
            self.current_text_block = None if ends_block else previous

    # -- page buffers ---------------------------------------------------------------------------

    @staticmethod
    def _wrap_markdown(el: Tag) -> str:
        """'**', '*' or '***' for an element bold and/or italic by tag or inline style."""
        style = (el.get("style") or "").lower()
        bold = "font-weight:700" in style or "font-weight:bold" in style or el.name in BOLD_TAGS
        italic = "font-style:italic" in style or el.name in ITALIC_TAGS
        return "***" if bold and italic else "**" if bold else "*" if italic else ""

    @staticmethod
    def _try_merge_inline_spans(last_text: str, current_text: str, last_source: Optional[Tag],
                                current_source: Optional[Tag]) -> Optional[str]:
        """Sibling spans of the same emphasis read as one: '**a** **b**' -> '**a b**'."""
        if not (isinstance(last_source, Tag) and isinstance(current_source, Tag)):
            return None
        if last_source.parent is not current_source.parent:
            return None

        last_stripped = last_text.rstrip()
        current_stripped = current_text.lstrip()
        last_ws = last_text[len(last_stripped):]
        current_ws = current_text[:len(current_text) - len(current_stripped)]
        if last_stripped.endswith("**") and current_stripped.startswith("**"):
            return last_stripped[:-2] + last_ws + current_ws + current_stripped[2:]
        if last_stripped.endswith("*") and current_stripped.startswith("*") and not last_stripped.endswith("**"):
            return last_stripped[:-1] + last_ws + current_ws + current_stripped[1:]
        return None

    def _append(self, page_num: int, s: str, source_node: Optional[Tag] = None) -> None:
        if not s:
            return
        buf = self.pages[page_num]
        seg_buf = self.page_segments[page_num]
        if buf and seg_buf:
            last_source, last_text_block = seg_buf[-1][1], seg_buf[-1][2]
            merged = self._try_merge_inline_spans(buf[-1], s, last_source, source_node)
            if merged:
                buf[-1] = merged
                seg_buf[-1] = (merged, last_source, last_text_block)
                return
        buf.append(s)
        seg_buf.append((s, source_node, self.current_text_block))

    def _blankline(self, page_num: int) -> None:
        """End the page's current line and leave one blank line (never two)."""
        buf = self.pages[page_num]
        seg_buf = self.page_segments[page_num]
        if not buf:
            return
        if not buf[-1].endswith("\n"):
            buf.append("\n")
            seg_buf.append(("\n", None, self.current_text_block))
        if len(buf) >= 2 and buf[-1] == "\n" and buf[-2] == "\n":
            return
        buf.append("\n")
        seg_buf.append(("\n", None, self.current_text_block))

    # -- rendering ------------------------------------------------------------------------------

    @staticmethod
    def _process_text_node(node: NavigableString) -> str:
        if isinstance(node, NOT_TEXT):
            return ""
        text = clean_text(str(node))
        return "" if text and _css_decl.match(text) else text

    @staticmethod
    def _img_to_markdown(el: Tag) -> str:
        src = el.get("src", "")
        return f"![{el.get('alt', '')}]({src})" if src else ""

    def _process_element(self, element: Union[Tag, NavigableString]) -> str:
        """An element rendered whole: text, a table, a list, an image."""
        if isinstance(element, NavigableString):
            return self._process_text_node(element)

        if element.name == "img":
            return self._img_to_markdown(element) if self.include_images else ""

        if element.name == "table":
            eff_rows = self._effective_rows(element)
            if len(eff_rows) <= 1:
                return self._one_row_table_to_text(eff_rows[0] if eff_rows else [])
            return TableParser(element).to_markdown().strip()

        if element.name in {"ul", "ol"}:
            items = []
            for li in element.find_all("li", recursive=False):
                item_text = self._process_element(li).strip()
                if item_text:
                    items.append(item_text.lstrip("•·∙◦▪▫-").strip())
            if element.name == "ol":
                return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
            return "\n".join(f"- {t}" for t in items)

        if element.name == "li":
            parts = [self._process_element(c) for c in element.children]
            return " ".join(p for p in parts if p).strip()

        parts = [self._process_element(child) for child in element.children]
        text = " ".join(p for p in parts if p).strip()
        if not text:
            return ""
        wrap = self._wrap_markdown(element)
        return f"{wrap}{text}{wrap}"

    def _effective_rows(self, table: Tag, limit: int = 2) -> list[list[Tag]]:
        """The first `limit` rows that have text: enough to tell a one-row table (rendered as text)."""
        rows = []
        for tr in iter_tags(table, ("tr",)):
            cells = ([c for c in tr.children if isinstance(c, Tag) and c.name in ("td", "th")]
                     or list(iter_tags(tr, ("td", "th"))))
            if any(clean_text(c.get_text(" ", strip=True)) for c in cells):
                rows.append(cells)
                if len(rows) == limit:
                    break
        return rows

    @staticmethod
    def _one_row_table_to_text(cells: list[Tag]) -> str:
        texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
        if not texts:
            return ""
        if m := ITEM_HEADER_CELL_RE.match(texts[0]):
            title = next((t for t in texts[1:] if t), "")
            return f"ITEM {m.group(1).upper()}. {title}".strip()
        if m := PART_HEADER_CELL_RE.match(texts[0]):
            return f"PART {m.group(1).upper()}"
        return " ".join(t for t in texts if t).strip()

    # -- position:absolute layouts --------------------------------------------------------------

    @staticmethod
    def _is_footer_element(el: Tag) -> bool:
        style = _style(el)
        if not ("position:absolute" in style and "bottom:0" in style):
            return False
        if "width:100%" in style:
            return True
        text = el.get_text(" ", strip=True)
        return bool(text) and len(text) < 200 and any(
            k in text.lower() for k in ("form 10-k", "form 10-q", "form 8-k", "page"))

    @staticmethod
    def _extract_page_number_from_footer(footer_el: Tag) -> Optional[int]:
        text = footer_el.get_text(" ", strip=True)
        if not text:
            return None
        for pattern, min_val in ((r"\|\s*(\d{1,4})\s*$", 1), (r"\bPage\s+(\d{1,4})\b", 1), (r"\b(\d{1,4})\s*$", 10)):
            m = re.search(pattern, text, re.IGNORECASE)
            if m and _plausible_page_number(int(m.group(1)), min_val):
                return int(m.group(1))
        return None

    @staticmethod
    def _extract_absolutely_positioned_children(container: Tag) -> List[Tag]:
        return [child for child in container.children
                if isinstance(child, Tag) and _is_absolute(_style(child))
                and (child.get_text(strip=True) or AbsolutelyPositionedTableParser._is_spacer(child))]

    @staticmethod
    def _split_positioned_groups(elements: List[Tag]) -> List[List[Tag]]:
        """Split positioned elements into vertical groups at gaps wider than ~1.2 lines."""
        if not elements:
            return []

        ys = sorted(y for y in map(_top_px, elements) if y is not None)
        line_gaps = [g for g in (b - a for a, b in zip(ys, ys[1:])) if 5 < g < 100]
        gap_threshold = min(1.2 * median(line_gaps), 30.0) if line_gaps else 30.0

        positioned = sorted(((y, el) for el in elements if (y := _top_px(el)) is not None), key=lambda x: x[0])
        if not positioned:
            return [elements]

        groups = []
        current = [positioned[0][1]]
        last_y = positioned[0][0]
        for y, el in positioned[1:]:
            if y - last_y > gap_threshold:
                groups.append(current)
                current = [el]
            else:
                current.append(el)
            last_y = y
        groups.append(current)

        return [part for group in groups for part in Parser._split_by_column_transition(group)]

    @staticmethod
    def _split_by_column_transition(elements: List[Tag]) -> List[List[Tag]]:
        """Split a group where it turns from a multi-column table into single-column text."""
        if len(elements) < 6:
            return [elements]

        element_data = []
        for el in elements:
            left_match = _LEFT_PX.search(el.get("style", ""))
            y = _top_px(el)
            if left_match and y is not None:
                element_data.append((float(left_match.group(1)), y, el))
        if not element_data:
            return [elements]
        element_data.sort(key=lambda x: x[1])

        rows = []
        current_row = [element_data[0]]
        last_y = element_data[0][1]
        for left, top, el in element_data[1:]:
            if abs(top - last_y) <= 15:
                current_row.append((left, top, el))
            else:
                rows.append(current_row)
                current_row = [(left, top, el)]
                last_y = top
        rows.append(current_row)

        columns = [len({left for left, _, _ in row}) for row in rows]
        split_point = None
        for i in range(len(rows) - 3):
            if columns[i] >= 2 and columns[i + 1] == 1 and sum(c == 1 for c in columns[i + 1:i + 4]) >= 2:
                split_point = i + 1
                break
        if split_point is None:
            return [elements]

        split_y = rows[split_point][0][1]
        groups = [[el for _, top, el in element_data if top < split_y],
                  [el for _, top, el in element_data if top >= split_y]]
        return [g for g in groups if g] or [elements]

    def _process_absolutely_positioned_container(self, container: Tag, page_num: int) -> int:
        positioned_children = self._extract_absolutely_positioned_children(container)
        if not positioned_children:
            for child in container.children:
                page_num = self._stream_pages(child, page_num)
            return page_num

        # Print-layout pages (e.g. 2026 S-1s) nest the page body in a normal-flow
        # wrapper NEXT TO positioned header/footer bands — stream those wrappers
        # first so the body is not dropped and reads before the page furniture.
        for child in container.children:
            if isinstance(child, Tag) and not _is_absolute(_style(child)):
                page_num = self._stream_pages(child, page_num)

        content_elements = []
        for child in positioned_children:
            if self._is_footer_element(child):
                display_page = self._extract_page_number_from_footer(child)
                if display_page is not None:
                    self.footer_page_numbers[page_num] = display_page
            else:
                content_elements.append(child)

        for i, group in enumerate(self._split_positioned_groups(content_elements)):
            table_parser = AbsolutelyPositionedTableParser(group)
            if table_parser.is_table_like():
                markdown_table = table_parser.to_markdown()
                if markdown_table:
                    self._append(page_num, markdown_table, source_node=group[0])
                    self._blankline(page_num)
            else:
                text = table_parser.to_text()
                if text:
                    if i > 0:
                        self._blankline(page_num)
                    self._append(page_num, text, source_node=group[0])
        return page_num

    # -- page breaks ----------------------------------------------------------------------------

    def _stylesheet_break_classes(self) -> Tuple[frozenset, frozenset]:
        """Classes a <style> rule breaks the page before / after, as pdf2htmlEX's
        .pf{page-break-after:always} in ESEF reports. Plain .class selectors only."""
        before, after = set(), set()
        for sheet in self.soup.find_all("style"):
            for selectors, declarations in _CSS_RULE.findall(sheet.get_text()):
                declarations = declarations.lower().replace(" ", "")
                breaks_before, breaks_after = _breaks_before(declarations), _breaks_after(declarations)
                if not (breaks_before or breaks_after):
                    continue
                for selector in selectors.split(","):
                    if m := _CLASS_SELECTOR.fullmatch(selector.strip()):
                        if breaks_before:
                            before.add(m.group(1))
                        if breaks_after:
                            after.add(m.group(1))
        return frozenset(before), frozenset(after)

    def _page_breaks(self, el: Tag, style: str) -> Tuple[bool, bool]:
        """Does the page break before / after the element: by inline style or stylesheet class.
        A content-visibility:auto container is one printed page (Workiva's print layout: no
        page-break styles, each page's furniture positioned by a CSS variable)."""
        before = _breaks_before(style)
        after = _breaks_after(style) or "content-visibility:auto" in style
        if self._classes_break_before or self._classes_break_after:
            classes = el.get("class") or ()
            before = before or not self._classes_break_before.isdisjoint(classes)
            after = after or not self._classes_break_after.isdisjoint(classes)
        return before, after

    # -- the walk -------------------------------------------------------------------------------

    def _stream_pages(self, root: Union[Tag, NavigableString], page_num: int = 1) -> int:
        """Walk the DOM once; split only on CSS break styles. Returns the page the walk ends on."""
        if isinstance(root, NavigableString):
            t = self._process_text_node(root)
            if t:
                self._append(page_num, t + " ", source_node=root.parent if isinstance(root.parent, Tag) else None)
            return page_num
        if not isinstance(root, Tag):
            return page_num

        style = _style(root)
        breaks_before, breaks_after = self._page_breaks(root, style)
        if breaks_before:
            page_num += 1
        if "display:none" in style:
            return page_num

        if root.name == "img" and self.include_images:
            md = self._img_to_markdown(root)
            if md:
                self._blankline(page_num)
                self._append(page_num, md, source_node=root)
                self._blankline(page_num)
            return page_num

        text_block_started = False
        text_block_has_continuation = False
        continuation_ends_text_block = False
        previous_text_block = self.current_text_block

        if root.name in ("ix:continuation", "continuation"):
            cont_id = root.get("id")
            if cont_id and cont_id in self.continuation_map:
                self.current_text_block = self.continuation_map[cont_id]
                text_block_started = True
                continuedat = root.get("continuedat")
                if continuedat:
                    text_block_has_continuation = True
                    self.continuation_map[continuedat] = self.current_text_block
                else:
                    continuation_ends_text_block = True

        def restore() -> None:
            self._restore_text_block(text_block_started, text_block_has_continuation,
                                     continuation_ends_text_block, previous_text_block)

        is_absolute = _is_absolute(style)
        if root.name == "div" and not is_absolute and any(
                isinstance(child, Tag) and _is_absolute(_style(child)) for child in root.children):
            page_num = self._process_absolutely_positioned_container(root, page_num)
            if breaks_after:
                page_num += 1
            restore()
            return page_num

        is_inline = "display:inline-block" in style or "display:inline;" in style
        is_block = root.name in BLOCK_TAGS and root.name not in {"br", "hr"} and not is_inline and not is_absolute

        # A block may open a new TextBlock (a new note replaces the previous one across pages).
        if is_block:
            tb_tag = self._find_text_block_tag_in_children(root)
            tb_info = self._extract_text_block_info(tb_tag) if tb_tag else None
            if tb_info and (self.current_text_block is None or self.current_text_block.name != tb_info.name):
                self.current_text_block = tb_info
                text_block_started = True
                continuedat = tb_tag.get("continuedat")
                if continuedat:
                    text_block_has_continuation = True
                    self.continuation_map[continuedat] = tb_info

        if is_block:
            self._blankline(page_num)

        if root.name in {"table", "ul", "ol"}:
            t = self._process_element(root)
            if t:
                self._append(page_num, t, source_node=root)
            self._blankline(page_num)
            # A table is rendered whole, so breaks inside it never reach the stream:
            # filings that put each page's footer (number | <p page-break-after> |
            # TOC link) in a table collapsed to ONE page. Count them here.
            # ponytail: the table lands on the page before its breaks; split the
            # table at the break row if mid-table breaks ever carry body content.
            for d in root.descendants:
                if isinstance(d, Tag) and (d.get("style") or d.get("class")):
                    page_num += any(self._page_breaks(d, _style(d)))
            if breaks_after:
                page_num += 1
            restore()
            return page_num

        wrap = self._wrap_markdown(root)
        if wrap and not is_block:
            t = self._process_element(root)
            if t:
                self._append(page_num, t + " ", source_node=root)
            if breaks_after:
                page_num += 1
            restore()
            return page_num

        for child in root.children:
            page_num = self._stream_pages(child, page_num)
        if is_block:
            self._blankline(page_num)
        if breaks_after:
            page_num += 1
        restore()
        return page_num

    # -- printed page numbers ---------------------------------------------------------------------

    def _detect_display_page_numbers(self, pages: List[Page]) -> List[Page]:
        """The page number printed on each page: from positioned footers, else from page text
        when the numbers found read as a sequence."""
        if self.footer_page_numbers:
            for page in pages:
                if page.number in self.footer_page_numbers:
                    page.display_page = self.footer_page_numbers[page.number]
            return pages

        candidates = [(page.number, self._extract_page_number_from_content(page.content)) for page in pages]
        if self._validate_page_number_sequence(candidates):
            for page in pages:
                if page.number - 1 < len(candidates):
                    page.display_page = candidates[page.number - 1][1]
        return pages

    @staticmethod
    def _extract_page_number_from_content(content: str) -> Optional[int]:
        if not content:
            return None
        lines = content.split("\n")
        for line in (lines[:3] + lines[-3:] if len(lines) >= 3 else lines):
            line = line.strip()
            if len(line) > 100:
                continue
            if re.match(r"^\d{1,4}$", line) and _plausible_page_number(int(line), min_val=10):
                return int(line)
            for pattern in _PAGE_NUMBER_PATTERNS:
                m = pattern.search(line)
                if m and _plausible_page_number(int(m.group(1))):
                    return int(m.group(1))
        return None

    @staticmethod
    def _validate_page_number_sequence(candidates: List[Tuple[int, Optional[int]]]) -> bool:
        """At least five numbers found, mostly counting up (consecutive numbers score double)."""
        found = [display for _, display in candidates if display is not None]
        if len(found) < 5:
            return False
        score = sum(2 if b == a + 1 else 1 if b > a else 0 for a, b in zip(found, found[1:]))
        return score / (len(found) - 1) >= 0.8

    @staticmethod
    def _strip_page_breadcrumbs(content: str) -> str:
        """Drop a bare 'PART II' + 'ITEM 7' breadcrumb repeated at the top of a page."""
        lines = content.split("\n")
        idx = 0
        for pattern in (_PART_BREADCRUMB, _ITEM_BREADCRUMB):
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            if idx >= len(lines) or not pattern.match(lines[idx].strip()):
                return content
            idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        return "\n".join(lines[idx:])

    # -- public API ---------------------------------------------------------------------------------

    def get_pages(self, include_elements: bool = True, include_images: bool = True) -> List[Page]:
        self.include_images = include_images
        self.pages = defaultdict(list)
        self.page_segments = defaultdict(list)
        self.footer_page_numbers = {}
        self.continuation_map = {}
        self.current_text_block = None
        self._classes_break_before, self._classes_break_after = self._stylesheet_break_classes()
        root = self.soup.body if self.soup.body else self.soup
        self._stream_pages(root, page_num=1)

        # Pages that came out empty (a break with nothing after it, two breaks in a row) are
        # dropped, the rest numbered from 1.
        result: List[Page] = []
        renumbered: Dict[int, int] = {}
        for walk_page in sorted(self.pages):
            raw = re.sub(r"\n{3,}", "\n\n", "".join(self.pages[walk_page]))
            lines: List[str] = []
            for line in raw.split("\n"):
                line = line.strip()
                if line or (lines and lines[-1]):
                    lines.append(line)
            content = self._strip_page_breadcrumbs("\n".join(lines).strip()).strip()
            if content:
                renumbered[walk_page] = len(result) + 1
                result.append(Page(number=len(result) + 1, content=content, elements=None))
        self.page_segments = {renumbered[n]: s for n, s in self.page_segments.items() if n in renumbered}
        self.footer_page_numbers = {renumbered[n]: d for n, d in self.footer_page_numbers.items() if n in renumbered}

        result = self._detect_display_page_numbers(result)
        if include_elements:
            result = self._add_elements_to_pages(result)
        return result

    def _add_elements_to_pages(self, pages: List[Page]) -> List[Page]:
        result, block_nodes_map = build_elements_for_pages(pages, self.page_segments)
        augment_html_with_ids({page.number: page.elements for page in result if page.elements}, block_nodes_map)
        # The highlight-on-hash script, so html() opens at a cited element (once)
        if self.soup.find("script", id="sec2md-highlight") is None:
            (self.soup.body or self.soup).append(BeautifulSoup(_HIGHLIGHT_SCRIPT, "html.parser"))
        return result

    def markdown(self) -> str:
        return "\n\n".join(page.content for page in self.get_pages() if page.content)

    def html(self) -> str:
        return str(self.soup)
