"""Property tests for both conventions on randomly generated structured C functions.

Graph/predicate invariants, default-switch deltas, merge invariance, and basis paths are audited."""

import random

import pytest

from conftest import analyze, fine
from test_paths import audit


class Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.n = 0

    def var(self):
        return self.r.choice("abcd")

    def cond(self, depth=0):
        k = self.r.random()
        if depth < 2 and k < 0.25:
            return f"({self.cond(depth+1)} {self.r.choice(['&&','||'])} {self.cond(depth+1)})"
        if depth < 2 and k < 0.32:
            return f"!({self.cond(depth+1)})"
        return f"{self.var()} {self.r.choice(['<','>','==','!='])} {self.r.randint(0, 9)}"

    def simple(self):
        self.n += 1
        k = self.r.random()
        if k < 0.1:
            return f"{self.var()} = {self.cond()} ? {self.r.randint(0,9)} : {self.r.randint(0,9)};"
        if k < 0.15:
            return f"{self.var()} = {self.cond()};"
        return f"{self.var()} += {self.n};"

    def stmts(self, depth, loop, switch):
        return " ".join(self.stmt(depth, loop, switch) for _ in range(self.r.randint(1, 3)))

    def stmt(self, depth, loop, switch):
        r = self.r.random()
        if depth >= 3 or r < 0.3:
            return self.simple()
        if r < 0.5:
            s = f"if ({self.cond()}) {{ {self.stmts(depth+1, loop, switch)} }}"
            if self.r.random() < 0.5:
                s += f" else {{ {self.stmts(depth+1, loop, switch)} }}"
            return s
        if r < 0.6:
            return f"while ({self.cond()}) {{ {self.stmts(depth+1, True, switch)} }}"
        if r < 0.68:
            return f"for (int i{depth} = 0; i{depth} < {self.r.randint(1,5)}; i{depth}++) {{ {self.stmts(depth+1, True, switch)} }}"
        if r < 0.74:
            return f"do {{ {self.stmts(depth+1, True, switch)} }} while ({self.cond()});"
        if r < 0.84:
            cases = []
            for v in range(self.r.randint(1, 4)):
                body = self.stmts(depth + 1, loop, True)
                tail = self.r.choice(["break;", "break;", ""])
                labels = f"case {v * 2}:"
                if self.r.random() < 0.35:
                    labels += f" case {v * 2 + 1}:"  # stacked labels
                cases.append(f"{labels} {body} {tail}")
            if self.r.random() < 0.5:
                cases.append(f"default: {self.stmts(depth+1, loop, True)}")
            return f"switch ({self.var()}) {{ {' '.join(cases)} }}"
        if r < 0.9 and loop:
            return f"if ({self.cond()}) {self.r.choice(['break;', 'continue;'])}"
        if r < 0.93 and switch:
            return f"if ({self.cond()}) break;"
        if r < 0.97:
            return f"if ({self.cond()}) return {self.r.randint(0,9)};"
        return self.simple()

    def program(self):
        return f"int f(int a, int b, int c, int d) {{ {self.stmts(0, False, False)} return a + b; }}"


SEEDS = range(400)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_program_invariants(seed):
    src = Gen(seed).program()
    r = analyze(src, convention="strict")
    course = analyze(src, convention="course")
    c = r["complexity"]
    # 1. structural count (from the syntax tree) agrees with the graph
    assert c["structural"]["agrees"], src
    # 2. E-N+2P agrees with 1 + branch contribution whenever EXIT is reachable
    if r["reachability"]["exit_reachable"]:
        assert c["formulas_agree"], src
    for result in (r, course):
        cx = result["complexity"]
        assert cx["value"] == cx["edges"] - cx["nodes"] + 2 * cx["components"], src
        assert cx["value"] == cx["predicate_value"] and cx["formulas_agree"], src
    default_switches = {
        n["id"] for n in r["graph"]["nodes"] if n["kind"] == "switch"
        and any(e["source"] == n["id"] and e["kind"] == "default" and e["label"] == "default" for e in r["graph"]["edges"])
    }
    assert course["complexity"]["value"] == c["value"] + len(default_switches), src
    # 3. merging basic blocks never changes M
    assert fine(src)["complexity"]["value"] == c["value"], src
    assert fine(src, convention="course")["complexity"]["value"] == course["complexity"]["value"], src
    # 4. basic graph sanity
    ids = {n["id"] for n in r["graph"]["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in r["graph"]["edges"])
    assert len({e["id"] for e in r["graph"]["edges"]}) == len(r["graph"]["edges"])
    out = {i: 0 for i in ids}
    for e in r["graph"]["edges"]:
        out[e["source"]] += 1
    assert all(d >= 1 for i, d in out.items() if i != r["graph"]["exit"]), src
    # 5. basis paths valid and independent whenever a terminating basis exists
    if r["paths"]["status"] == "complete":
        audit(r)
    else:
        assert r["paths"]["status"] in ("unavailable", "skipped")
