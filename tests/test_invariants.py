"""Properties every parse must have, checked on every fixture filing (tests/snapshot.py)."""
import re

import pytest

import sec2md
from sec2md import Parser

from tests.snapshot import FIXTURES, load_html, parse

HTML_LEFTOVER = re.compile(r"</?(?:div|span|td|tr|th|table|font|p|br|ix:[a-z]+)\b[^>]*>", re.I)


@pytest.fixture(params=list(FIXTURES))
def fixture(request):
    return request.param


def test_pages_are_numbered_from_one_and_none_is_empty(fixture):
    pages = parse(fixture)[0]
    assert [p.number for p in pages] == list(range(1, len(pages) + 1))
    assert all(p.content.strip() for p in pages)


def test_no_html_or_comment_markers_leak(fixture):
    for p in parse(fixture)[0]:
        assert not HTML_LEFTOVER.search(p.content), (p.number, HTML_LEFTOVER.search(p.content).group())
        assert "Field: Page" not in p.content and "Field: Set" not in p.content


def test_elements_are_unique_and_point_into_their_page(fixture):
    seen = set()
    for p in parse(fixture)[0]:
        for e in p.elements or []:
            assert e.id not in seen
            seen.add(e.id)
            assert e.id.startswith(f"sec2md-p{p.number}-") and e.page_start == e.page_end == p.number
            if e.content_start_offset is not None:
                assert p.content[e.content_start_offset:e.content_end_offset] == e.content


def test_markdown_is_the_pages_joined(fixture):
    pages = parse(fixture)[0]
    assert sec2md.convert_to_markdown(load_html(fixture)) == "\n\n".join(p.content for p in pages if p.content)


def test_get_pages_twice_gives_the_same_pages_and_html(fixture):
    parser = Parser(load_html(fixture))
    first = [(p.content, [e.id for e in p.elements or []]) for p in parser.get_pages()]
    html = parser.html()
    second = [(p.content, [e.id for e in p.elements or []]) for p in parser.get_pages()]
    same_pages, same_html = first == second, parser.html() == html  # no assert diff of MBs of HTML
    assert same_pages and same_html


def test_chunks_cite_real_elements(fixture):
    pages, _, chunks, _ = parse(fixture)
    ids = {e.id for p in pages for e in p.elements or []}
    assert [c.index for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert c.content.strip()
        assert all(eid.split(":part-")[0] in ids for eid in c.element_ids)


def test_sections_are_ordered_and_inside_the_filing(fixture):
    pages, sections, _, _ = parse(fixture)
    starts = [s.page_range[0] for s in sections]
    assert starts == sorted(starts)
    assert all(1 <= s.page_range[0] <= s.page_range[1] <= len(pages) for s in sections)
