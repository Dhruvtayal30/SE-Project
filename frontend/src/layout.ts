// Layout only decides WHERE things are drawn. It never changes graph semantics or metrics.
import dagre from "@dagrejs/dagre";
import type { CfgEdge, CfgNode } from "./types";

export type Direction = "TB" | "LR";
export interface NodeBox { id: string; x: number; y: number; w: number; h: number; lines: string[] }
export interface EdgePath { id: string; points: { x: number; y: number }[]; label: { x: number; y: number } | null }
export interface Layout { nodes: Record<string, NodeBox>; edges: Record<string, EdgePath>; width: number; height: number }

const CHAR_W = 7.2, LINE_H = 17, MAX_LINES = 6, MAX_CHARS = 34;

export function displayLines(n: CfgNode): string[] {
  if (n.kind === "entry" || n.kind === "exit") return [n.label];
  const clip = (s: string, max: number) => (s.length > max ? s.slice(0, max - 1) + "…" : s);
  if (n.kind === "decision" || n.kind === "switch") return [clip(n.statements[0]?.text ?? n.label, 26) + (n.kind === "decision" ? " ?" : "")];
  const all = n.statements.map((s) => clip(s.text, MAX_CHARS));
  if (all.length <= MAX_LINES) return all;
  return [...all.slice(0, MAX_LINES - 1), `… +${all.length - MAX_LINES + 1} more`];
}

export function boxSize(n: CfgNode): { w: number; h: number; lines: string[] } {
  const lines = displayLines(n);
  const textW = Math.max(...lines.map((l) => l.length)) * CHAR_W;
  if (n.kind === "entry" || n.kind === "exit") return { w: Math.max(96, textW + 40), h: 38, lines };
  if (n.kind === "decision" || n.kind === "switch") return { w: Math.max(150, textW * 1.7 + 30), h: 76, lines };
  return { w: Math.max(110, textW + 28), h: lines.length * LINE_H + 22, lines };
}

export function computeLayout(nodes: CfgNode[], edges: CfgEdge[], dir: Direction = "TB"): Layout {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: dir, nodesep: dir === "TB" ? 46 : 36, ranksep: dir === "TB" ? 56 : 80, edgesep: 24, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));
  const boxes: Record<string, NodeBox> = {};
  for (const n of nodes) {
    const { w, h, lines } = boxSize(n);
    boxes[n.id] = { id: n.id, x: 0, y: 0, w, h, lines };
    g.setNode(n.id, { width: w, height: h });
  }
  for (const e of edges) {
    const text = e.label || "";
    g.setEdge(e.source, e.target, { width: text ? text.length * 6.2 + 10 : 0, height: text ? 16 : 0, labelpos: "c" }, e.id);
  }
  dagre.layout(g);
  const out: Layout = { nodes: boxes, edges: {}, width: 0, height: 0 };
  for (const n of nodes) {
    const p = g.node(n.id);
    boxes[n.id].x = p.x - p.width / 2;
    boxes[n.id].y = p.y - p.height / 2;
  }
  for (const e of edges) {
    const d = g.edge({ v: e.source, w: e.target, name: e.id });
    const pts = (d.points ?? []).map((p: { x: number; y: number }) => ({ x: p.x, y: p.y }));
    out.edges[e.id] = { id: e.id, points: clipEndpoints(pts, boxes[e.source], boxes[e.target], nodes), label: e.label ? { x: d.x, y: d.y } : null };
  }
  const gr = g.graph();
  out.width = gr.width ?? 0;
  out.height = gr.height ?? 0;
  routeBackEdges(out, edges, dir);
  return out;
}

/** Diamonds are drawn inside their bounding box, so pull edge ends onto the diamond outline. */
function clipEndpoints(pts: { x: number; y: number }[], s: NodeBox, t: NodeBox, nodes: CfgNode[]) {
  if (pts.length < 2) return pts;
  const kind = (id: string) => nodes.find((n) => n.id === id)?.kind;
  const clip = (box: NodeBox, from: { x: number; y: number }, k?: string) => {
    if (k !== "decision" && k !== "switch") return null;
    const cx = box.x + box.w / 2, cy = box.y + box.h / 2, dx = from.x - cx, dy = from.y - cy;
    const f = Math.abs(dx) / (box.w / 2) + Math.abs(dy) / (box.h / 2);
    return f === 0 ? null : { x: cx + dx / f, y: cy + dy / f };
  };
  const out = pts.slice();
  const a = clip(s, pts[1], kind(s.id)); if (a) out[0] = a;
  const b = clip(t, pts[pts.length - 2], kind(t.id)); if (b) out[out.length - 1] = b;
  return out;
}

/** Smooth path through dagre's routed points (Catmull-Rom converted to cubic Béziers). */
export function pathFromPoints(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return "";
  if (pts.length === 2) return `M${pts[0].x},${pts[0].y} L${pts[1].x},${pts[1].y}`;
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] ?? p2;
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    d += ` C${c1.x},${c1.y} ${c2.x},${c2.y} ${p2.x},${p2.y}`;
  }
  return d;
}

/**
 * Loop (back) edges: dagre routes them diagonally through the drawing. Route them around the outside instead:
 * leave the source on the free side, run alongside the graph, and re-enter the loop header.
 */
function routeBackEdges(out: Layout, edges: CfgEdge[], dir: Direction) {
  let lane = 0;
  for (const e of edges.filter((x) => x.back_edge)) {
    const s = out.nodes[e.source], t = out.nodes[e.target];
    const cx = (b: NodeBox) => b.x + b.w / 2, cy = (b: NodeBox) => b.y + b.h / 2;
    const gap = 30 + lane * 16;
    lane = (lane + 1) % 6;
    let pts: { x: number; y: number }[], label: { x: number; y: number };
    if (dir === "TB") {
      const lo = Math.min(s.y, t.y) - 4, hi = Math.max(s.y + s.h, t.y + t.h) + 4;
      let right = Math.max(s.x + s.w, t.x + t.w), left = Math.min(s.x, t.x);
      for (const b of Object.values(out.nodes)) if (b.y < hi && b.y + b.h > lo) { right = Math.max(right, b.x + b.w); left = Math.min(left, b.x); }
      // take whichever side needs the shorter detour
      const useLeft = Math.min(s.x, t.x) - left < right - Math.max(s.x + s.w, t.x + t.w);
      const X = useLeft ? left - gap : right + gap;
      const sx = useLeft ? s.x : s.x + s.w, tx = useLeft ? t.x : t.x + t.w;
      const sy = cy(s), ty = cy(t);
      pts = e.source === e.target
        ? [{ x: sx, y: sy - 8 }, { x: X, y: sy - 18 }, { x: X, y: sy + 18 }, { x: sx, y: sy + 8 }]
        : [{ x: sx, y: sy }, { x: X, y: sy }, { x: X, y: ty }, { x: tx, y: ty }];
      label = { x: X, y: (pts[1].y + pts[2].y) / 2 };
    } else {
      const lo = Math.min(s.x, t.x) - 4, hi = Math.max(s.x + s.w, t.x + t.w) + 4;
      let bottom = Math.max(s.y + s.h, t.y + t.h);
      for (const b of Object.values(out.nodes)) if (b.x < hi && b.x + b.w > lo) bottom = Math.max(bottom, b.y + b.h);
      const Y = bottom + gap;
      pts = e.source === e.target
        ? [{ x: cx(s) - 8, y: s.y + s.h }, { x: cx(s) - 18, y: Y }, { x: cx(s) + 18, y: Y }, { x: cx(s) + 8, y: s.y + s.h }]
        : [{ x: cx(s), y: s.y + s.h }, { x: cx(s), y: Y }, { x: cx(t), y: Y }, { x: cx(t), y: t.y + t.h }];
      label = { x: (pts[1].x + pts[2].x) / 2, y: Y };
      out.height = Math.max(out.height, Y + 30);
    }
    out.edges[e.id] = { id: e.id, points: pts, label: e.label ? label : null };
  }
}
