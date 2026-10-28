import type { AnalysisResult } from "../types";

function Check({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <li className={ok ? "check ok" : "check warn"}>
      <span className="check-mark" aria-hidden>{ok ? "✓" : "!"}</span>
      <span><strong>{label}</strong><span className="muted"> {detail}</span></span>
    </li>
  );
}

export default function MetricsPanel({ result, convention = result.convention, onConventionChange }: {
  result: AnalysisResult; convention?: "strict" | "course"; onConventionChange?: (convention: "strict" | "course") => void;
}) {
  const c = result.complexity, s = result.statistics, r = result.reachability;
  const predicateCount = c.predicate_count ?? Math.max(0, c.branch_value - 1);
  const predicateValue = c.predicate_value ?? c.branch_value;
  const predicateBreakdown = c.predicate_breakdown ?? {};
  return (
    <div className="panel-body" data-testid="metrics-panel">
      <section className={`m-hero band-${c.interpretation.band}`}>
        <div className="m-value" data-testid="m-value" aria-label={`Cyclomatic complexity ${c.value}`}>{c.value}</div>
        <div>
          <div className="m-title">Cyclomatic complexity</div>
          <div className="m-band">{c.interpretation.label}</div>
        </div>
      </section>
      <p className="muted small">{c.interpretation.text}</p>

      <label className="convention-toggle">
        <input type="checkbox" checked={convention === "course"} onChange={(e) => onConventionChange?.(e.target.checked ? "course" : "strict")} />
        <span>Count `default` as a decision (course convention)</span>
      </label>
      <p className="muted small convention-note">Strict McCabe differs by exactly the number of switches that have a `default`.</p>

      <h3>How it was calculated</h3>
      <div className="formula" data-testid="formula">
        <div className="f-name">{c.formula} <span className="muted">(reachable graph · {c.convention_label ?? (convention === "course" ? "Course convention" : "Strict McCabe")})</span></div>
        <div className="f-calc">{c.substituted}</div>
        <div className="f-name">{c.predicate_formula ?? "M = P_d + 1"}</div>
        <div className="f-calc">{c.predicate_substituted ?? `M = ${predicateCount} + 1 = ${predicateValue}`}</div>
      </div>
      <p className="muted small">
        N = {c.nodes} reachable nodes (ENTRY and EXIT included), E = {c.edges} edges, P = {c.components} connected component.
        Each edge keeps its own identity, so a True and a False edge to the same node count twice.
      </p>
      <p className="small predicate-list" data-testid="predicate-list">
        Predicates: {Object.entries(predicateBreakdown).map(([k, v]) => `${k.replace("do_while", "do-while")}: ${v}`).join(" · ") || "none"}
      </p>

      <h3>Consistency checks</h3>
      <ul className="checks">
        <Check ok={c.formulas_agree} label="Graph formula = predicate formula" detail={c.formulas_agree ? `both give ${c.value}` : `${c.value} vs ${predicateValue}: ${r.exit_reachable ? "see warning" : "no reachable EXIT; see notes"}`} />
        <Check ok={c.branch_value === c.value} label={c.branch_formula} detail={c.branch_value === c.value ? `both give ${c.branch_value}` : `${c.value} vs ${c.branch_value}`} />
        <Check ok={c.structural.agrees} label="Syntax-tree decision count" detail={`1 + ${c.structural.decisions} = ${c.structural.value} (independent of the graph builder)`} />
      </ul>
      {c.applicability.map((a) => <div key={a.code} className="note" role="note"><strong>Note.</strong> {a.message}</div>)}

      <h3>Graph statistics</h3>
      <table className="kv">
        <tbody>
          <tr><th>Nodes (reachable / total)</th><td>{s.nodes_reachable} / {s.nodes_total}</td></tr>
          <tr><th>Edges (reachable / total)</th><td>{c.edges} / {s.edges_total}</td></tr>
          <tr><th>Basic blocks</th><td>{s.basic_blocks}</td></tr>
          <tr><th>Decision nodes</th><td>{s.decision_nodes}{s.switch_nodes ? ` (incl. ${s.switch_nodes} switch)` : ""}</td></tr>
          <tr><th>Branch contribution Σ(outdeg − 1)</th><td>{c.branch_contribution}</td></tr>
          <tr><th>Loops (back edges)</th><td>{s.loops}</td></tr>
          <tr><th>Function length</th><td>{s.function_lines} lines</td></tr>
        </tbody>
      </table>

      <h3>Reachability</h3>
      <table className="kv">
        <tbody>
          <tr><th>Reachable from ENTRY</th><td>{r.reachable_percent}%</td></tr>
          <tr><th>EXIT reachable</th><td>{r.exit_reachable ? "yes" : "no — function never returns"}</td></tr>
          <tr><th>Unreachable nodes</th><td>{r.unreachable_nodes.length || "none"}</td></tr>
          <tr><th>Nodes that cannot reach EXIT</th><td>{r.trapped_nodes.length || "none"}</td></tr>
        </tbody>
      </table>
      <h3>Decision breakdown (syntax tree)</h3>
      <p className="small">{Object.entries(c.structural.breakdown).filter(([, v]) => v > 0).map(([k, v]) => `${v} × ${k}`).join(", ") || "no decisions"}</p>
    </div>
  );
}
