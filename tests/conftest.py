import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from cfg_analyzer.analyzer import analyze_source  # noqa: E402
from cfg_analyzer.api import create_app  # noqa: E402
from cfg_analyzer.validation import validate_request  # noqa: E402


def analyze(source: str, **kw):
    """Run the pipeline; legacy analysis tests use strict convention unless specified."""
    payload = {"source": source, "convention": kw.pop("convention", "strict")}
    if "function" in kw:
        payload["function"] = kw.pop("function")
    if kw:
        payload["options"] = kw
    return analyze_source(validate_request(payload))


def fine(source: str, **kw):
    """One node per statement/condition (no basic-block merging): easiest to assert semantically."""
    return analyze(source, merge_blocks=False, **kw)


def labels(r):
    return {n["id"]: n["label"] for n in r["graph"]["nodes"]}


def edge_set(r):
    """{(source text, edge label, target text)} -- semantic view of the graph."""
    lab = labels(r)
    return {(lab[e["source"]], e["label"], lab[e["target"]]) for e in r["graph"]["edges"]}


def node_by_label(r, text):
    hits = [n for n in r["graph"]["nodes"] if n["label"] == text]
    assert len(hits) == 1, f"{text!r}: {len(hits)} nodes"
    return hits[0]


def rank_of(vectors):
    """Independent exact rank (dense Gaussian elimination over Fractions) used to audit basis paths."""
    rows = [[Fraction(x) for x in v] for v in vectors]
    rank, ncols = 0, len(rows[0]) if rows else 0
    for c in range(ncols):
        piv = next((i for i in range(rank, len(rows)) if rows[i][c] != 0), None)
        if piv is None:
            continue
        rows[rank], rows[piv] = rows[piv], rows[rank]
        for i in range(len(rows)):
            if i != rank and rows[i][c] != 0:
                f = rows[i][c] / rows[rank][c]
                rows[i] = [a - f * b for a, b in zip(rows[i], rows[rank])]
        rank += 1
    return rank


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()
