import { pathFromPoints, type Layout } from "./layout";
import type { AnalysisResult, CfgNode } from "./types";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const FILL: Record<string, string> = { entry: "#e8eee8", exit: "#e8eee8", block: "#ffffff", decision: "#f5efdc", switch: "#eee5c9" };

function shape(n: CfgNode, b: Layout["nodes"][string]): string {
  const stroke = n.reachable ? "#64746a" : "#aab2aa";
  const dash = n.reachable ? "" : ' stroke-dasharray="5 4"';
  const fill = n.reachable ? FILL[n.kind] : "#f1f2ef";
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  if (n.kind === "decision" || n.kind === "switch")
    return `<polygon points="${cx},${b.y} ${b.x + b.w},${cy} ${cx},${b.y + b.h} ${b.x},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="1.6"${dash}/>`;
  const r = n.kind === "entry" || n.kind === "exit" ? b.h / 2 : 6;
  return `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1.6"${dash}/>`;
}

/** A standalone SVG built from the same graph + layout the UI shows (no DOM screenshots). */
export function toSvg(result: AnalysisResult, layout: Layout, highlight?: { nodes: Set<string>; edges: Set<string> }): string {
  const pad = 16, W = layout.width + pad * 2, H = layout.height + pad * 2;
  const dim = (on: boolean) => (highlight && highlight.nodes.size + highlight.edges.size > 0 && !on ? ' opacity="0.25"' : "");
  const parts: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="${-pad} ${-pad} ${W} ${H}" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="12">`,
    `<title>CFG of ${esc(result.function.name)} — M = ${result.complexity.value}</title>`,
    `<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#69766d"/></marker></defs>`,
    `<rect x="${-pad}" y="${-pad}" width="${W}" height="${H}" fill="#ffffff"/>`,
  ];
  for (const e of result.graph.edges) {
    const p = layout.edges[e.id];
    if (!p) continue;
    const hot = highlight?.edges.has(e.id) ?? false;
    const color = hot ? "#527260" : e.reachable ? "#69766d" : "#aab2aa";
    parts.push(`<g${dim(hot)}><path d="${pathFromPoints(p.points)}" fill="none" stroke="${color}" stroke-width="${hot ? 2.6 : 1.5}"${e.reachable ? "" : ' stroke-dasharray="5 4"'} marker-end="url(#a)"/>`);
    if (p.label && e.label) parts.push(`<text x="${p.label.x}" y="${p.label.y + 4}" text-anchor="middle" font-size="11" fill="#0f172a" stroke="#fff" stroke-width="3" paint-order="stroke">${esc(e.label)}</text>`);
    parts.push("</g>");
  }
  for (const n of result.graph.nodes) {
    const b = layout.nodes[n.id];
    const cx = b.x + b.w / 2, lh = 17, top = b.y + b.h / 2 - ((b.lines.length - 1) * lh) / 2 + 4;
    const anchor = n.kind === "block" ? "start" : "middle";
    parts.push(`<g${dim(highlight?.nodes.has(n.id) ?? false)}>${shape(n, b)}`);
    b.lines.forEach((l, i) => parts.push(`<text x="${anchor === "start" ? b.x + 12 : cx}" y="${top + i * lh}" text-anchor="${anchor}" fill="#0f172a">${esc(l)}</text>`));
    parts.push("</g>");
  }
  parts.push("</svg>");
  return parts.join("");
}

export async function svgToPngBlob(svg: string, scale = 2): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((ok, bad) => { img.onload = () => ok(); img.onerror = () => bad(new Error("SVG could not be rasterised")); img.src = url; });
    const canvas = document.createElement("canvas");
    canvas.width = img.width * scale; canvas.height = img.height * scale;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(scale, scale); ctx.drawImage(img, 0, 0);
    return await new Promise<Blob>((ok, bad) => canvas.toBlob((b) => (b ? ok(b) : bad(new Error("PNG encoding failed"))), "image/png"));
  } finally { URL.revokeObjectURL(url); }
}

export function summaryMarkdown(r: AnalysisResult): string {
  const c = r.complexity, s = r.statistics;
  const L = [
    `# CFG analysis: \`${r.function.name}\``, "", `\`${r.function.signature}\` (lines ${r.function.start_line}–${r.function.end_line})`, "",
    "## Metrics", "",
    `| Metric | Value |`, `|---|---|`,
    `| Nodes (reachable / total) | ${s.nodes_reachable} / ${s.nodes_total} |`, `| Edges (reachable / total) | ${c.edges} / ${s.edges_total} |`,
    `| Decision nodes | ${s.decision_nodes} |`, `| Loops (back edges) | ${s.loops} |`,
    `| **Cyclomatic complexity** | **${c.value}** (${c.interpretation.label}) |`, "",
    `- ${c.formula}: ${c.substituted}`, `- ${c.branch_formula}: ${c.branch_substituted}`,
    `- Syntax-tree cross-check: ${c.structural.value} (${c.structural.agrees ? "agrees" : "DISAGREES"})`, "",
  ];
  if (c.applicability.length) { L.push("## Notes", ""); c.applicability.forEach((a) => L.push(`- ${a.message}`)); L.push(""); }
  L.push("## Independent paths", "");
  if (r.paths.paths.length === 0) L.push(`Not available: ${r.paths.reason ?? r.paths.status}`);
  const label = new Map(r.graph.nodes.map((n) => [n.id, n.index]));
  r.paths.paths.forEach((p) => L.push(`${p.index}. ${p.nodes.map((id) => `N${label.get(id)}`).join(" → ")}${p.decisions.length ? "  [" + p.decisions.map((d) => `N${label.get(d.node)}:${d.label}`).join(", ") + "]" : ""}`));
  L.push("", "_Paths are structural: branch conditions are not solved, so a path may be infeasible._");
  if (r.warnings.length) { L.push("", "## Warnings", ""); r.warnings.forEach((w) => L.push(`- [${w.severity}] ${w.line ? `line ${w.line}: ` : ""}${w.message}`)); }
  return L.join("\n") + "\n";
}

export function download(name: string, blob: Blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
