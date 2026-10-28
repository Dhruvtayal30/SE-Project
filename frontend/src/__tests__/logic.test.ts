import { describe, expect, it, vi, afterEach } from "vitest";
import { AnalysisFailure, analyze } from "../api";
import { summaryMarkdown, toSvg } from "../exportGraph";
import { computeLayout, pathFromPoints } from "../layout";
import { linesForNodes, nodesForLines, shortestPathTo } from "../sourceMap";
import { deadResult, infiniteResult, loopResult, switchResult } from "./helpers";

const lay = (r = switchResult, dir: "TB" | "LR" = "TB") => computeLayout(r.graph.nodes, r.graph.edges, dir);

describe("layout", () => {
  it("places every node and edge, deterministically", () => {
    const a = lay(), b = lay();
    expect(Object.keys(a.nodes)).toHaveLength(switchResult.graph.nodes.length);
    expect(Object.keys(a.edges)).toHaveLength(switchResult.graph.edges.length);
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });
  it("never overlaps two nodes", () => {
    const boxes = Object.values(lay().nodes);
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const p = boxes[i], q = boxes[j];
      const overlap = p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h;
      expect(overlap, `${p.id} overlaps ${q.id}`).toBe(false);
    }
  });
  it("TB flows downwards from ENTRY to EXIT, LR flows rightwards", () => {
    const g = switchResult.graph;
    const tb = lay(), lr = lay(switchResult, "LR");
    expect(tb.nodes[g.exit].y).toBeGreaterThan(tb.nodes[g.entry].y);
    expect(lr.nodes[g.exit].x).toBeGreaterThan(lr.nodes[g.entry].x);
  });
  it("every edge has a drawable path and labelled edges have a label position", () => {
    const l = lay();
    for (const e of switchResult.graph.edges) {
      expect(l.edges[e.id].points.length).toBeGreaterThanOrEqual(2);
      expect(pathFromPoints(l.edges[e.id].points)).toMatch(/^M/);
      if (e.label) expect(l.edges[e.id].label).not.toBeNull();
    }
  });
  it("routes loop back edges outside the node column and ends them at the loop header", () => {
    const back = loopResult.graph.edges.find((e) => e.back_edge)!;
    const l = lay(loopResult);
    const pts = l.edges[back.id].points, target = l.nodes[back.target];
    const rightMost = Math.max(...Object.values(l.nodes).map((b) => b.x + b.w));
    const leftMost = Math.min(...Object.values(l.nodes).map((b) => b.x));
    expect(pts.some((p) => p.x > rightMost || p.x < leftMost)).toBe(true);
    const end = pts[pts.length - 1];
    expect(Math.abs(end.y - (target.y + target.h / 2))).toBeLessThan(1);
  });
  it("keeps parallel edges as separate paths", () => {
    const e = switchResult.graph.edges;
    const pairs = new Map<string, string[]>();
    e.forEach((x) => pairs.set(x.source + ">" + x.target, [...(pairs.get(x.source + ">" + x.target) ?? []), x.id]));
    const l = lay();
    for (const ids of pairs.values()) expect(new Set(ids.map((i) => JSON.stringify(l.edges[i].points))).size).toBe(ids.length);
  });
});

describe("source mapping", () => {
  it("maps a line to its nodes and back", () => {
    const node = switchResult.graph.nodes.find((n) => n.statements[0]?.text === "i % 2 == 0")!;
    const line = node.lines[0];
    expect(nodesForLines(switchResult, line, line)).toContain(node.id);
    expect(linesForNodes(switchResult, [node.id])).toEqual(node.lines);
  });
  it("short-circuit conditions on one line map to several nodes", () => {
    const ids = nodesForLines(switchResult, 18, 18);
    expect(ids.length).toBe(2);
  });
  it("rebuilds the shortest path from ENTRY using backend parent edges", () => {
    const target = switchResult.graph.nodes.find((n) => n.kind === "exit")!;
    const p = shortestPathTo(switchResult, target.id)!;
    expect(p.nodes[0]).toBe(switchResult.graph.entry);
    expect(p.nodes[p.nodes.length - 1]).toBe(target.id);
    expect(p.edges).toHaveLength(target.distance!);
  });
  it("has no path to an unreachable node", () => {
    const dead = deadResult.graph.nodes.find((n) => !n.reachable)!;
    expect(shortestPathTo(deadResult, dead.id)).toBeNull();
  });
});

describe("exports", () => {
  it("produces well-formed SVG with one shape and label per element", () => {
    const svg = toSvg(switchResult, lay());
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
    expect(doc.querySelector("parsererror")).toBeNull();
    expect(doc.querySelectorAll("path[marker-end]").length).toBe(switchResult.graph.edges.length);
    expect(doc.querySelectorAll("polygon").length).toBe(switchResult.graph.nodes.filter((n) => n.kind === "decision" || n.kind === "switch").length);
    expect(svg).toContain("M = 8");
  });
  it("escapes source text", () => {
    const r = structuredClone(switchResult);
    r.graph.nodes[1].statements[0].text = "a < b && c > d";
    const l = lay(r);
    l.nodes[r.graph.nodes[1].id].lines = ["a < b && c > d"];
    const svg = toSvg(r, l);
    expect(svg).toContain("a &lt; b &amp;&amp; c &gt; d");
    expect(new DOMParser().parseFromString(svg, "image/svg+xml").querySelector("parsererror")).toBeNull();
  });
  it("dims everything outside a highlighted path", () => {
    const p = loopResult.paths.paths[1];
    const svg = toSvg(loopResult, lay(loopResult), { nodes: new Set(p.nodes), edges: new Set(p.edges) });
    expect(svg).toContain('opacity="0.25"');
  });
  it("summary states the backend's numbers", () => {
    const md = summaryMarkdown(switchResult);
    expect(md).toContain("**8**");
    expect(md).toContain(switchResult.complexity.substituted);
    expect(md.match(/^\d+\. /gm)).toHaveLength(8);
    expect(summaryMarkdown(infiniteResult)).toContain("Not available");
  });
});

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("returns the analysis on success", async () => {
    const result = structuredClone(switchResult);
    result.convention = "course";
    result.complexity.convention = "course";
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(result), { status: 200 })));
    expect((await analyze("x", { mergeBlocks: true })).complexity.value).toBe(8);
  });
  it("rejects a response that did not apply the requested convention", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(switchResult), { status: 200 })));
    const err = await analyze("x", { mergeBlocks: true, convention: "course" }).catch((e) => e);
    expect(err).toBeInstanceOf(AnalysisFailure);
    expect(err.error.code).toBe("CONVENTION_MISMATCH");
    expect(err.message).toMatch(/restart the backend/i);
  });
  it("turns structured server errors into AnalysisFailure with locations", async () => {
    const body = { ok: false, error: { code: "SYNTAX_ERROR", message: "bad", locations: [{ line: 2, column: 5, message: "missing ';'" }] } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 422 })));
    const err = await analyze("x", { mergeBlocks: true }).catch((e) => e);
    expect(err).toBeInstanceOf(AnalysisFailure);
    expect(err.error.locations[0].line).toBe(2);
    expect(err.status).toBe(422);
  });
  it("explains a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed"); }));
    const err = await analyze("x", { mergeBlocks: true }).catch((e) => e);
    expect(err.error.code).toBe("NETWORK");
    expect(err.message).toMatch(/backend/i);
  });
  it("copes with a non-JSON response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>502</html>", { status: 502 })));
    const err = await analyze("x", { mergeBlocks: true }).catch((e) => e);
    expect(err.error.code).toBe("BAD_RESPONSE");
  });
});
