import type { AnalysisResult, CfgNode } from "../types";

interface Props {
  result: AnalysisResult; node: CfgNode | null; onSelectNode: (id: string) => void;
  onShowShortest: (id: string) => void; onJumpLine: (line: number) => void;
}

export default function NodeDetails({ result, node, onSelectNode, onShowShortest, onJumpLine }: Props) {
  if (!node) return <div className="panel-body empty" data-testid="node-empty"><p>Select a node in the graph, or click a line in the editor, to inspect it.</p></div>;
  const byId = new Map(result.graph.nodes.map((n) => [n.id, n]));
  const incoming = result.graph.edges.filter((e) => e.target === node.id);
  const outgoing = result.graph.edges.filter((e) => e.source === node.id);
  const short = (id: string) => { const n = byId.get(id)!; return n.kind === "entry" ? "ENTRY" : n.kind === "exit" ? "EXIT" : `n${n.index}`; };
  const edgeRow = (e: typeof incoming[number], other: string) => (
    <li key={e.id}>
      <button className="link" onClick={() => onSelectNode(other)}>{short(other)}</button>
      <span className={`pill pill-${e.kind}`}>{e.label || "next"}</span>
      {e.back_edge && <span className="pill pill-back">loop back edge</span>}
      {!e.reachable && <span className="pill pill-dead">unreachable</span>}
    </li>
  );
  return (
    <div className="panel-body" data-testid="node-details">
      <h2 className="node-title"><span className="mono">{short(node.id)}</span> {node.role}</h2>
      <p className="small">{node.explanation}</p>
      {node.loop_header && <p className="note small">This node is a loop header: a back edge returns here.</p>}
      {!node.reachable && <p className="note warn small">Unreachable: no path from ENTRY leads here. It is excluded from the complexity calculation.</p>}
      {node.reachable && !node.can_reach_exit && <p className="note warn small">Control entering here can never reach EXIT (infinite loop).</p>}

      <h3>Statements</h3>
      {node.statements.length === 0 || node.kind === "entry" || node.kind === "exit"
        ? <p className="muted small">Synthetic node (no source statements).</p>
        : <ol className="stmts">{node.statements.map((s, i) => (
            <li key={i}><button className="link mono-link" onClick={() => onJumpLine(s.line)}>line {s.line}</button><code>{s.text}</code></li>))}</ol>}

      <h3>Edges</h3>
      <div className="edge-cols">
        <div><h4>Incoming ({incoming.length})</h4><ul className="edge-list">{incoming.length ? incoming.map((e) => edgeRow(e, e.source)) : <li className="muted">none</li>}</ul></div>
        <div><h4>Outgoing ({outgoing.length})</h4><ul className="edge-list">{outgoing.length ? outgoing.map((e) => edgeRow(e, e.target)) : <li className="muted">none</li>}</ul></div>
      </div>

      {node.reachable && node.kind !== "entry" && (
        <>
          <h3>Shortest path from ENTRY</h3>
          <p className="small">{node.distance} edge{node.distance === 1 ? "" : "s"} <button className="btn small-btn" onClick={() => onShowShortest(node.id)}>Highlight</button></p>
        </>
      )}
    </div>
  );
}
