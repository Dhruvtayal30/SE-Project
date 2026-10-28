import type { Warning } from "../types";

const ICON = { error: "✕ Error", warning: "▲ Warning", info: "ℹ Info" } as const;

export default function WarningsPanel({ warnings, assumptions, onJump }: { warnings: Warning[]; assumptions: string[]; onJump: (line: number, node?: string | null) => void }) {
  return (
    <div className="panel-body" data-testid="warnings-panel">
      {warnings.length === 0 && <p className="muted">No warnings for this function.</p>}
      <ul className="warnings">
        {warnings.map((w, i) => (
          <li key={i} className={`warn-item sev-${w.severity}`}>
            <div className="warn-head"><span className="sev">{ICON[w.severity]}</span><span className="mono small">{w.code}</span>
              {w.line && <button className="link" onClick={() => onJump(w.line!, w.node)}>line {w.line}</button>}</div>
            <div className="small">{w.message}</div>
          </li>
        ))}
      </ul>
      <h3>Assumptions</h3>
      <ul className="small bullets">{assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
    </div>
  );
}
