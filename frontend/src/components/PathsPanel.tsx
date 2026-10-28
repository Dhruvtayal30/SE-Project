import type { AnalysisResult } from "../types";

interface Props { result: AnalysisResult; selected: number | null; onSelect: (index: number | null) => void }

export default function PathsPanel({ result, selected, onSelect }: Props) {
  const p = result.paths;
  const idx = new Map(result.graph.nodes.map((n) => [n.id, n]));
  const nm = (id: string) => { const n = idx.get(id)!; return n.kind === "entry" ? "ENTRY" : n.kind === "exit" ? "EXIT" : `n${n.index}`; };
  return (
    <div className="panel-body" data-testid="paths-panel">
      <p className="small">
        A basis of <strong>{p.expected}</strong> independent ENTRY→EXIT paths (= M). Independence means the edge-usage vectors are linearly
        independent (exact rational arithmetic). Every other path is a combination of these.
      </p>
      {p.paths.length === 0 && <div className="note warn" role="note" data-testid="paths-unavailable"><strong>Not available.</strong> {p.reason ?? `Status: ${p.status}.`}</div>}
      {p.status === "partial" && <div className="note warn">{p.reason}</div>}
      {p.paths.length > 0 && (
        <>
          <div className="row-between"><span className="muted small">{p.paths.length} paths · rank {p.rank} = M</span>
            <button className="btn small-btn" onClick={() => onSelect(null)} disabled={selected === null}>Clear highlight</button></div>
          <ol className="paths">
            {p.paths.map((path) => (
              <li key={path.index}>
                <button className={`path-card ${selected === path.index ? "active" : ""}`} onClick={() => onSelect(selected === path.index ? null : path.index)} data-testid={`path-${path.index}`}>
                  <div className="path-head"><strong>P{path.index}</strong><span className="muted small">{path.length} edges{path.repeats_nodes ? " · loop traversal" : ""}</span></div>
                  <div className="path-seq mono">{path.nodes.map(nm).join(" → ")}</div>
                  {path.decisions.length > 0 && <div className="chips">{path.decisions.map((d, i) => <span key={i} className="chip">{nm(d.node)}: {d.label}</span>)}</div>}
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="muted small">Paths are <em>structural</em>. Branch conditions are not solved, so a listed path may be infeasible for every input.</p>
    </div>
  );
}
