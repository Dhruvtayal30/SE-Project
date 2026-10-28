import type { AnalysisResult } from "./types";

/** Nodes whose source lines intersect [from, to] (1-based, inclusive). Order follows the graph. */
export function nodesForLines(result: AnalysisResult, from: number, to: number): string[] {
  const hit = new Set<string>();
  const map = result.source_map.line_to_nodes;
  for (let l = Math.min(from, to); l <= Math.max(from, to); l++) (map[String(l)] ?? []).forEach((id) => hit.add(id));
  return result.graph.nodes.filter((n) => hit.has(n.id)).map((n) => n.id);
}

export function linesForNodes(result: AnalysisResult, ids: Iterable<string>): number[] {
  const set = new Set(ids);
  const lines = new Set<number>();
  for (const n of result.graph.nodes) if (set.has(n.id)) n.lines.forEach((l) => lines.add(l));
  return [...lines].sort((a, b) => a - b);
}

/** Walk parent edges (computed by the backend) to rebuild the shortest structural path from ENTRY. */
export function shortestPathTo(result: AnalysisResult, nodeId: string): { nodes: string[]; edges: string[] } | null {
  const byId = new Map(result.graph.nodes.map((n) => [n.id, n]));
  const edgeById = new Map(result.graph.edges.map((e) => [e.id, e]));
  const nodes = [nodeId], edges: string[] = [];
  let cur = byId.get(nodeId);
  if (!cur || !cur.reachable) return null;
  while (cur && cur.parent_edge) {
    const e = edgeById.get(cur.parent_edge)!;
    edges.unshift(e.id);
    nodes.unshift(e.source);
    cur = byId.get(e.source);
  }
  return { nodes, edges };
}
