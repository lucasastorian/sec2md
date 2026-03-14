"""Element extraction: groups parsed page segments into semantic blocks.

Takes the raw segments produced by Parser._stream_pages() and builds
structured Element and TextBlock objects for each page.
"""

from __future__ import annotations

import re
import hashlib
from typing import List, Dict, Optional, Tuple, Any

from bs4.element import Tag

from sec2md.models import Page, Element, TextBlock


def build_elements_for_pages(
    pages: List[Page],
    page_segments: Dict[int, List[Tuple[str, Optional[Tag], Any]]],
    min_chars: int = 500,
) -> Tuple[List[Page], Dict[str, List[Tag]]]:
    """Build Elements and TextBlocks for pages from parsed segments.

    Args:
        pages: Parsed pages (content already set).
        page_segments: Per-page segment tuples (content, source_node, text_block_info).
        min_chars: Minimum characters before flushing a merged block.

    Returns:
        (augmented_pages, block_nodes_map) where block_nodes_map maps
        element IDs to their source DOM nodes (for HTML augmentation).
    """
    page_elements: Dict[int, List[Element]] = {}
    page_text_blocks: Dict[int, List[TextBlock]] = {}
    block_nodes_map: Dict[str, List[Tag]] = {}

    for page in pages:
        page_num = page.number
        segments = page_segments.get(page_num, [])

        if not segments:
            page_elements[page_num] = []
            page_text_blocks[page_num] = []
            continue

        blocks_with_nodes = _group_segments_into_blocks(segments, page_num)
        merged_blocks = _merge_small_blocks(blocks_with_nodes, page_num, min_chars=min_chars)

        elements = []
        text_block_map: Dict[str, List[str]] = {}

        for element, nodes, text_block_info in merged_blocks:
            elements.append(element)
            block_nodes_map[element.id] = nodes

            if text_block_info:
                tb_name = text_block_info.name
                if tb_name not in text_block_map:
                    text_block_map[tb_name] = []
                text_block_map[tb_name].append(element.id)

        # Compute content offsets
        page_content = page.content
        current_offset = 0
        for element in elements:
            search_text = element.content[:min(100, len(element.content))]
            idx = page_content.find(search_text, current_offset)

            if idx >= 0:
                element.content_start_offset = idx
                element.content_end_offset = idx + len(element.content)
                current_offset = element.content_end_offset
            else:
                element.content_start_offset = None
                element.content_end_offset = None

        page_elements[page_num] = elements

        # Build TextBlock objects
        seen_names = {}
        for element, nodes, text_block_info in merged_blocks:
            if text_block_info and text_block_info.name not in seen_names:
                seen_names[text_block_info.name] = text_block_info

        element_map = {elem.id: elem for elem in elements}
        text_blocks = []

        for tb_name, tb_info in seen_names.items():
            element_ids = text_block_map.get(tb_name, [])
            if element_ids:
                tb_elements = [element_map[eid] for eid in element_ids if eid in element_map]
                text_blocks.append(TextBlock(
                    name=tb_name,
                    title=tb_info.title,
                    elements=tb_elements
                ))

        page_text_blocks[page_num] = text_blocks

    result = []
    for page in pages:
        elements = page_elements.get(page.number, [])
        text_blocks = page_text_blocks.get(page.number, [])
        result.append(Page(
            number=page.number,
            content=page.content,
            elements=elements if elements else None,
            text_blocks=text_blocks if text_blocks else None,
            display_page=page.display_page
        ))

    return result, block_nodes_map


def augment_html_with_ids(
    page_elements: Dict[int, List[Element]],
    block_nodes_map: Dict[str, List[Tag]],
) -> None:
    """Add id attributes and data-sec2md-block to source DOM nodes."""
    seen_pages: set = set()

    for page_num in sorted(page_elements.keys()):
        elements = page_elements[page_num]

        for element in elements:
            nodes = block_nodes_map.get(element.id, [])
            if not nodes:
                continue

            first_node = nodes[0]

            if page_num not in seen_pages:
                if 'id' in first_node.attrs:
                    existing_classes = first_node.get('class', [])
                    if isinstance(existing_classes, str):
                        existing_classes = existing_classes.split()
                    existing_classes.append(f"page-{page_num}")
                    first_node['class'] = existing_classes
                else:
                    first_node['id'] = f"page-{page_num}"
                seen_pages.add(page_num)

            if 'id' not in first_node.attrs:
                first_node['id'] = element.id

            for node in nodes:
                node['data-sec2md-block'] = element.id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_bold_header(element: Element) -> bool:
    """Check if element is a bold header (section boundary marker)."""
    content = element.content.strip()

    if not (content.startswith('**') and '**' in content[2:]):
        return False

    first_line = content.split('\n')[0].strip()

    if first_line.startswith('**') and first_line.endswith('**'):
        bold_text = first_line[2:-2].strip()
        if len(bold_text) < 50 and bold_text.count('.') <= 1:
            return True

    return False


def _generate_block_id(page: int, idx: int, content: str, kind: str) -> str:
    """Generate stable block ID using normalized content hash."""
    normalized = re.sub(r'\s+', ' ', content.strip()).lower()
    hash_part = hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:8]
    kind_prefix = kind[0] if kind else "b"
    return f"sec2md-p{page}-{kind_prefix}{idx}-{hash_part}"


def _infer_kind_from_nodes(nodes: List[Tag]) -> str:
    """Infer block kind from DOM nodes."""
    if not nodes:
        return "text"

    for node in nodes:
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "header"
        elif node.name == "table":
            return "table"
        elif node.name in {"ul", "ol"}:
            return "list"
        elif node.name == "p":
            return "paragraph"

    return "text"


def _create_block(
    segments: List[str],
    nodes: List[Tag],
    page_num: int,
    block_idx: int,
) -> Optional[Element]:
    """Create an Element from segments and nodes."""
    content = "".join(segments).strip()
    if not content:
        return None

    kind = _infer_kind_from_nodes(nodes)
    block_id = _generate_block_id(page_num, block_idx, content, kind)

    return Element(
        id=block_id,
        content=content,
        kind=kind,
        page_start=page_num,
        page_end=page_num
    )


def _group_segments_into_blocks(
    segments: List[Tuple[str, Optional[Tag], Any]],
    page_num: int,
) -> List[Tuple[Element, List[Tag], Any]]:
    """Group sequential segments into semantic blocks (split on double newlines)."""
    blocks = []
    current_block_segments: List[str] = []
    current_block_nodes: List[Tag] = []
    current_text_block = None
    block_idx = 0

    for content, node, text_block in segments:
        if content == "\n":
            if current_block_segments and current_block_segments[-1] == "\n":
                if len(current_block_segments) > 1:
                    block = _create_block(
                        current_block_segments[:-1],
                        current_block_nodes,
                        page_num,
                        block_idx
                    )
                    if block:
                        blocks.append((block, list(current_block_nodes), current_text_block))
                        block_idx += 1
                current_block_segments = []
                current_block_nodes = []
                current_text_block = None
                continue

        current_block_segments.append(content)
        if node is not None and node not in current_block_nodes:
            current_block_nodes.append(node)
        if text_block is not None:
            current_text_block = text_block

    if current_block_segments:
        while current_block_segments and current_block_segments[-1] == "\n":
            current_block_segments.pop()

        if current_block_segments:
            block = _create_block(
                current_block_segments,
                current_block_nodes,
                page_num,
                block_idx
            )
            if block:
                blocks.append((block, list(current_block_nodes), current_text_block))

    return blocks


def _merge_small_blocks(
    blocks_with_nodes: List[Tuple[Element, List[Tag], Any]],
    page_num: int,
    min_chars: int = 500,
) -> List[Tuple[Element, List[Tag], Any]]:
    """Merge consecutive small blocks into larger semantic units."""
    if not blocks_with_nodes:
        return []

    merged: List[Tuple[Element, List[Tag], Any]] = []
    current_elements: List[Element] = []
    current_nodes: List[Tag] = []
    current_chars = 0
    current_text_block = None

    def flush(block_idx: int):
        nonlocal current_elements, current_nodes, current_chars
        if not current_elements:
            return

        merged_content = '\n\n'.join(e.content for e in current_elements)

        kinds = [e.kind for e in current_elements]
        if 'table' in kinds:
            kind = 'table'
        elif 'header' in kinds:
            kind = 'section'
        else:
            kind = current_elements[0].kind

        block_id = _generate_block_id(page_num, block_idx, merged_content, kind)

        merged_element = Element(
            id=block_id,
            content=merged_content,
            kind=kind,
            page_start=page_num,
            page_end=page_num
        )

        merged.append((merged_element, list(current_nodes), current_text_block))
        current_elements = []
        current_nodes = []
        current_chars = 0

    for i, (element, nodes, text_block) in enumerate(blocks_with_nodes):
        text_block_changed = False
        if current_text_block is not None or text_block is not None:
            if current_text_block is None and text_block is not None:
                text_block_changed = True
            elif current_text_block is not None and text_block is None:
                text_block_changed = True
            elif current_text_block is not None and text_block is not None:
                text_block_changed = current_text_block.name != text_block.name

        if text_block_changed and current_elements:
            flush(len(merged))

        current_text_block = text_block

        if element.kind == 'table':
            if current_elements and current_chars < min_chars:
                current_elements.append(element)
                current_nodes.extend([n for n in nodes if n not in current_nodes])
                flush(len(merged))
            else:
                flush(len(merged))
                merged.append((element, nodes, text_block))
            continue

        bold_header = _is_bold_header(element)

        # Flush before bold headers (section boundaries), but keep headers with content
        if bold_header and current_elements:
            all_headers = all(_is_bold_header(e) for e in current_elements)
            is_current_only_headers = all_headers and current_chars < 200

            if not is_current_only_headers:
                flush(len(merged))

        current_elements.append(element)
        current_nodes.extend([n for n in nodes if n not in current_nodes])
        current_chars += element.char_count

        should_flush = False

        if current_chars >= min_chars:
            should_flush = True

        if i + 1 < len(blocks_with_nodes):
            next_element, _, _ = blocks_with_nodes[i + 1]
            if _is_bold_header(next_element):
                should_flush = True

        if i == len(blocks_with_nodes) - 1:
            should_flush = True

        if should_flush:
            all_headers = all(_is_bold_header(e) for e in current_elements)
            is_only_headers = all_headers and current_chars < 200

            if not is_only_headers:
                flush(len(merged))

    if current_elements:
        flush(len(merged))

    return merged
