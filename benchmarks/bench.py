"""Run sec2md over a corpus of filings: timings, output metrics and output hashes per document.

    python benchmarks/bench.py run -j 8 -o before.json          # corpus: benchmarks/corpus/
    python benchmarks/bench.py run --dump out/before            # also write outputs, for diff -r
    python benchmarks/bench.py run --quality -o q.json          # + table cells lost per document
    python benchmarks/bench.py compare before.json after.json

A refactor must leave every hash unchanged; an improvement shows up as a reviewed diff. The corpus
is any directory of .html/.htm/.xhtml files (optionally .gz); a file named <FORM>__<id>.html.gz
also gets section extraction for that form (10-K, 10-Q, 20-F, 8-K, amendments as their base form).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import sec2md
from sec2md import Parser

CORPUS = Path(__file__).parent / "corpus"
SECTION_FORMS = {"10-K": "10-K", "10-KT": "10-K", "10-Q": "10-Q", "20-F": "20-F", "8-K": "8-K"}
TRIVIAL = {"$", "%", ")", "(", "•", "●", "◦", "▪", "·", "-", "–", "—"}


def _read(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return data.decode("utf-8", "replace")


def _filing_type(path: Path) -> str | None:
    form = path.name.split("__")[0].replace("_A", "") if "__" in path.name else ""
    return SECTION_FORMS.get(form)


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _render(pages, sections, chunks) -> dict[str, str]:
    """Every output as text: what the hashes cover and --dump writes."""
    md = "\n".join(f"<<page {p.number} display={p.display_page}>>\n{p.content}" for p in pages)
    elements = []
    for p in pages:
        for e in p.elements or []:
            elements.append(json.dumps([e.id, e.kind, e.page_start, e.page_end, e.content_start_offset,
                                        e.content_end_offset, e.tags, e.content], ensure_ascii=False))
        for tb in p.text_blocks or []:
            elements.append(json.dumps(["textblock", p.number, tb.name, tb.title, tb.element_ids], ensure_ascii=False))
    secs = [json.dumps([s.part, s.item, s.item_title, list(s.page_range),
                        [x.model_dump() for x in s.exhibits or []], s.markdown()], ensure_ascii=False)
            for s in sections or []]
    def render(chunks):
        return [json.dumps([c.index, c.page_range, c.display_page_range, c.element_ids, c.content], ensure_ascii=False)
                for c in chunks]
    # beyond whole pages: each section's chunks, each XBRL note's chunks
    section_chunks = [line for s in sections or [] for line in render(sec2md.chunk_section(s))]
    note_chunks = [line for tb in sec2md.merge_text_blocks(pages)
                   for line in [tb.name] + render(sec2md.chunk_text_block(tb))]
    return {"md": md, "elements": "\n".join(elements), "sections": "\n".join(secs),
            "chunks": "\n".join(render(chunks)), "section_chunks": "\n".join(section_chunks),
            "note_chunks": "\n".join(note_chunks)}


def _lost_cells(html: str) -> tuple[int, int]:
    """(tables, cells lost): a visible table's non-trivial cell text missing from its markdown."""
    from bs4 import BeautifulSoup
    from sec2md.table_parser import TableParser

    norm = lambda t: re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()
    tables = lost = 0
    for t in BeautifulSoup(html, "lxml").find_all("table"):
        if t.find_parent("table") or any("display:none" in (a.get("style") or "").replace(" ", "").lower()
                                         for a in t.parents if hasattr(a, "get")):
            continue
        cells = {norm(td.get_text(" ")) for td in t.find_all(["td", "th"])} - TRIVIAL - {""}
        if len(t.find_all("tr")) < 2 or not cells:
            continue
        md = norm(TableParser(t).to_markdown().replace("\\|", " ").replace("|", " ").replace("**", ""))
        tables += 1
        lost += sum(c not in md for c in cells)
    return tables, lost


def run_one(args: tuple[str, bool, str | None]) -> tuple[str, dict]:
    path, quality, dump = Path(args[0]), args[1], args[2]
    name = path.name.split(".")[0]
    try:
        html = _read(path)
        t0 = time.perf_counter()
        parser = Parser(html)
        t1 = time.perf_counter()
        pages = parser.get_pages()
        t2 = time.perf_counter()
        ftype = _filing_type(path)
        sections = sec2md.extract_sections(pages, filing_type=ftype) if ftype else None
        t3 = time.perf_counter()
        chunks = sec2md.chunk_pages(pages)
        t4 = time.perf_counter()
        out = _render(pages, sections, chunks)
        out["html"] = parser.html()
        rec = {
            "bytes": len(html), "pages": len(pages),
            "elements": sum(len(p.elements or []) for p in pages),
            "chars": sum(len(p.content) for p in pages),
            "tables": sum(p.content.count("\n| ---") for p in pages),
            "sections": None if sections is None else len(sections), "chunks": len(chunks),
            "t_soup": t1 - t0, "t_pages": t2 - t1, "t_sections": t3 - t2, "t_chunks": t4 - t3,
            "sha": {k: _sha(v) for k, v in out.items()},
        }
        if quality:
            rec["q_tables"], rec["q_lost_cells"] = _lost_cells(html)
        if dump:
            d = Path(dump)
            d.mkdir(parents=True, exist_ok=True)
            for k, v in out.items():
                if k != "html":
                    (d / f"{name}.{k}.txt").write_text(v, encoding="utf-8")
        return name, rec
    except Exception:
        return name, {"error": traceback.format_exc(limit=3)[-600:]}


def cmd_run(a) -> None:
    corpus = Path(a.corpus)
    paths = sorted(p for p in corpus.rglob("*") if re.search(r"\.(x?html?)(\.gz)?$", p.name))
    if a.match:
        paths = [p for p in paths if re.search(a.match, str(p.relative_to(corpus)))]
    paths = paths[: a.limit or None]
    jobs = [(str(p), a.quality, a.dump) for p in paths]
    t = time.perf_counter()
    if a.jobs > 1:
        with ProcessPoolExecutor(a.jobs) as ex:
            results = dict(ex.map(run_one, jobs, chunksize=2))
    else:
        results = dict(map(run_one, jobs))
    wall = time.perf_counter() - t
    out = {"sec2md": sec2md.__version__, "jobs": a.jobs, "wall": wall, "docs": results}
    Path(a.output).write_text(json.dumps(out, indent=1, sort_keys=True))
    errors = [n for n, r in results.items() if "error" in r]
    print(f"{len(results)} docs in {wall:.1f}s wall ({a.jobs} jobs), {len(errors)} errors -> {a.output}")
    _summary(results)


def _summary(docs: dict) -> None:
    ok = [r for r in docs.values() if "error" not in r]
    keys = ["pages", "elements", "tables", "chunks", "q_lost_cells"]
    print("  " + "  ".join(f"{k}={sum(r.get(k) or 0 for r in ok):,}" for k in keys if any(k in r for r in ok)))
    t = {k: sum(r[k] for r in ok) for k in ("t_soup", "t_pages", "t_sections", "t_chunks")}
    print("  cpu: " + "  ".join(f"{k[2:]}={v:.1f}s" for k, v in t.items()) + f"  total={sum(t.values()):.1f}s")


def cmd_compare(a) -> None:
    old, new = (json.loads(Path(p).read_text())["docs"] for p in (a.old, a.new))
    changed: dict[str, list[str]] = {}
    for name in sorted(set(old) | set(new)):
        o, n = old.get(name), new.get(name)
        if o is None or n is None:
            changed.setdefault("missing", []).append(name)
        elif ("error" in o) != ("error" in n):
            changed.setdefault("fixed" if "error" in o else "broke", []).append(name)
        elif "error" not in o:
            for k in o["sha"]:
                if o["sha"][k] != n["sha"].get(k):
                    changed.setdefault(k, []).append(name)
    if not changed:
        print(f"identical: all {len(new)} documents, every output")
    for k, names in changed.items():
        print(f"{k:9} {len(names):4} changed: {' '.join(names[:12])}{' ...' if len(names) > 12 else ''}")
    print("old:"); _summary(old)
    print("new:"); _summary(new)
    for k in ("t_soup", "t_pages", "t_sections", "t_chunks"):
        so = sum(r[k] for r in old.values() if "error" not in r)
        sn = sum(r[k] for r in new.values() if "error" not in r)
        print(f"  {k[2:]:9} {so:7.1f}s -> {sn:7.1f}s  ({sn / so if so else 0:.2f}x)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--corpus", default=str(CORPUS))
    r.add_argument("-o", "--output", default="bench.json")
    r.add_argument("-j", "--jobs", type=int, default=1)
    r.add_argument("--match", help="regex on the path relative to the corpus")
    r.add_argument("--limit", type=int)
    r.add_argument("--quality", action="store_true", help="also count table cells lost (slower)")
    r.add_argument("--dump", help="directory to write every output to, for diff -r")
    c = sub.add_parser("compare")
    c.add_argument("old")
    c.add_argument("new")
    a = ap.parse_args()
    sys.setrecursionlimit(10000)
    (cmd_run if a.cmd == "run" else cmd_compare)(a)


if __name__ == "__main__":
    main()
