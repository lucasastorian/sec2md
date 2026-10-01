"""Every fixture filing's output, byte for byte, against tests/golden (see tests/snapshot.py)."""
import difflib
import json

import pytest

import sec2md
from sec2md import Item10K

from tests.snapshot import FIXTURES, GOLDEN_DIR, parse, render


def _assert_same(expected: str, actual: str, name: str) -> None:
    if expected == actual:
        return
    diff = "".join(difflib.unified_diff(expected.splitlines(keepends=True), actual.splitlines(keepends=True),
                                        f"golden/{name}", f"current/{name}", n=2))
    pytest.fail(f"{name} differs from its golden (python -m tests.snapshot to regenerate):\n{diff[:6000]}")


@pytest.mark.parametrize("name", FIXTURES)
def test_markdown(name):
    md, _ = render(name)
    _assert_same((GOLDEN_DIR / f"{name}.md").read_text(encoding="utf-8"), md, f"{name}.md")


@pytest.mark.parametrize("name", FIXTURES)
def test_structure(name):
    _, structure = render(name)
    actual = json.dumps(structure, indent=1, ensure_ascii=False) + "\n"
    _assert_same((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"), actual, f"{name}.json")


# The README's examples, on the README's filing.

def test_readme_risk_factors():
    pages, sections, _, _ = parse("aapl_10k")
    risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
    assert risk.item == "ITEM 1A" and risk.part == "PART I"
    assert risk.markdown().startswith("Item 1A. Risk Factors\n\nThe Company’s business, reputation")


def test_readme_chunk_section_with_header():
    _, sections, _, _ = parse("aapl_10k")
    risk = sec2md.get_section(sections, Item10K.RISK_FACTORS)
    header = "Apple Inc. (AAPL)\nForm 10-K | FY 2024 | Risk Factors"
    chunks = sec2md.chunk_section(risk, chunk_size=512, header=header)
    assert len(chunks) > 10
    assert all(c.embedding_text.startswith(header + "\n\n...\n\n") for c in chunks)
