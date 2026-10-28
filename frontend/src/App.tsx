import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnalysisFailure, analyze, loadExamples } from "./api";
import CfgGraph from "./components/CfgGraph";
import CodeEditor, { type Marks } from "./components/CodeEditor";
import Legend from "./components/Legend";
import MetricsPanel from "./components/MetricsPanel";
import Methodology from "./components/Methodology";
import NodeDetails from "./components/NodeDetails";
import PathsPanel from "./components/PathsPanel";
import WarningsPanel from "./components/WarningsPanel";
import { download, summaryMarkdown, svgToPngBlob, toSvg } from "./exportGraph";
import { computeLayout, type Direction } from "./layout";
import { linesForNodes, nodesForLines, shortestPathTo } from "./sourceMap";
import type { AnalysisResult, ApiError, ExampleItem } from "./types";

type Tab = "metrics" | "node" | "paths" | "warnings";
type MobileView = "code" | "graph" | "details";
const MAX_FILE_CHARS = 100_000;
const STARTER = `#include <stdio.h>

int process(int n, int mode) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        if (i % 2 == 0 && mode > 0) {
            continue;
        }
        switch (mode) {
            case 1:
                total += i;
                break;
            case 2:
                total += 2 * i;
            case 3:
                total += 3;
                break;
            default:
                total -= 1;
        }
        if (total > 100)
            break;
    }
    while (total > 50) {
        total -= 10;
    }
    return total > 0 ? total : 0;
}
`;

export default function App() {
  const [source, setSource] = useState(STARTER);
  const [examples, setExamples] = useState<ExampleItem[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [analyzed, setAnalyzed] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [mergeBlocks, setMergeBlocks] = useState(true);
  const [convention, setConvention] = useState<"strict" | "course">("course");
  const [dir, setDir] = useState<Direction>("TB");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [pathIndex, setPathIndex] = useState<number | null>(null);
  const [shortest, setShortest] = useState<{ nodes: string[]; edges: string[] } | null>(null);
  const [tab, setTab] = useState<Tab>("metrics");
  const [view, setView] = useState<MobileView>("code");
  const [scrollTo, setScrollTo] = useState<{ line: number; nonce: number } | null>(null);
  const [resetNonce, setResetNonce] = useState(0);
  const [graphExpanded, setGraphExpanded] = useState(false);
  const [menu, setMenu] = useState<null | "examples" | "export">(null);
  const [showMethod, setShowMethod] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const seq = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!graphExpanded) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") setGraphExpanded(false); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [graphExpanded]);

  const flash = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(null), 3500); }, []);

  const run = useCallback(async (src: string, fn?: string | null, merge = mergeBlocks, conv = convention) => {
    abort.current?.abort();
    const ctl = new AbortController(); abort.current = ctl;
    const mine = ++seq.current;
    setLoading(true);
    try {
      const r = await analyze(src, { fn, mergeBlocks: merge, convention: conv }, ctl.signal);
      if (mine !== seq.current) return;
      setResult(r); setAnalyzed(src); setError(null);
      setSelected(new Set()); setSelectedEdge(null); setPathIndex(null); setShortest(null); setTab("metrics"); setView("graph");
    } catch (e) {
      if ((e as Error).name === "AbortError" || mine !== seq.current) return;
      setResult(null); setAnalyzed(null);
      setError(e instanceof AnalysisFailure ? e.error : { code: "UNKNOWN", message: (e as Error).message });
      setView("graph");
    } finally { if (mine === seq.current) setLoading(false); }
  }, [mergeBlocks, convention]);

  // First load: populate the examples menu; wait for the user to request analysis.
  useEffect(() => {
    loadExamples().then(setExamples).catch(() => setExamples([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const stale = result !== null && analyzed !== source;
  const layout = useMemo(() => (result ? computeLayout(result.graph.nodes, result.graph.edges, dir) : null), [result, dir]);

  const path = useMemo(() => {
    if (!result) return null;
    if (shortest) return shortest;
    const p = pathIndex ? result.paths.paths.find((x) => x.index === pathIndex) : null;
    return p ? { nodes: p.nodes, edges: p.edges } : null;
  }, [result, pathIndex, shortest]);
  const pathNodes = useMemo(() => new Set(path?.nodes ?? []), [path]);
  const pathEdges = useMemo(() => new Set(path?.edges ?? []), [path]);

  const selectNodes = useCallback((ids: string[], keepTab = false) => {
    setSelected(new Set(ids)); setSelectedEdge(null);
    if (ids.length && !keepTab) setTab("node");
    if (ids.length) setView((v) => (v === "code" ? v : "details"));
  }, []);

  const onSelectNode = useCallback((id: string | null) => {
    if (id) { setPathIndex(null); setShortest(null); selectNodes([id]); } else { setSelected(new Set()); }
  }, [selectNodes]);

  const onSelectLines = useCallback((from: number, to: number) => {
    if (!result || stale) return;
    const ids = nodesForLines(result, from, to);
    if (ids.length) { setPathIndex(null); setShortest(null); selectNodes(ids); }
  }, [result, stale, selectNodes]);

  const jumpLine = useCallback((line: number, nodeId?: string | null) => {
    setScrollTo({ line, nonce: Date.now() });
    if (nodeId) selectNodes([nodeId]);
    setView("code");
  }, [selectNodes]);

  const marks = useMemo<Marks>(() => {
    const errors = (error?.locations ?? []).map((l) => l.line);
    if (!result || stale) return { active: [], errors, dead: [] };
    const dead = linesForNodes(result, result.graph.nodes.filter((n) => !n.reachable).map((n) => n.id));
    const active = linesForNodes(result, selected);
    return { active, errors, dead: dead.filter((l) => !active.includes(l)) };
  }, [result, selected, error, stale]);

  const selectedNode = result && selected.size ? result.graph.nodes.find((n) => n.id === [...selected][0]) ?? null : null;
  useEffect(() => { if (selectedNode && selectedNode.lines[0]) setScrollTo({ line: selectedNode.lines[0], nonce: Date.now() }); }, [selectedNode?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadExample = (ex: ExampleItem) => { setMenu(null); setSource(ex.source); run(ex.source, ex.function); };
  const newAnalysis = () => { setMenu(null); abort.current?.abort(); seq.current++; setSource(""); setResult(null); setAnalyzed(null); setError(null); setLoading(false); setView("code"); };
  const onFile = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_FILE_CHARS * 4) return flash(`File is too large (limit ${MAX_FILE_CHARS.toLocaleString()} characters).`);
    const text = await f.text();
    if (text.length > MAX_FILE_CHARS) return flash(`File has ${text.length.toLocaleString()} characters; the limit is ${MAX_FILE_CHARS.toLocaleString()}.`);
    setSource(text); run(text);
  };

  const exportAs = async (kind: "svg" | "png" | "json" | "md") => {
    setMenu(null);
    if (!result || !layout) return;
    const base = `cfg-${result.function.name}`;
    const hl = path ? { nodes: pathNodes, edges: pathEdges } : undefined;
    try {
      if (kind === "json") download(`${base}.json`, new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
      else if (kind === "md") download(`${base}-summary.md`, new Blob([summaryMarkdown(result)], { type: "text/markdown" }));
      else if (kind === "svg") download(`${base}.svg`, new Blob([toSvg(result, layout, hl)], { type: "image/svg+xml" }));
      else download(`${base}.png`, await svgToPngBlob(toSvg(result, layout, hl)));
    } catch (e) { flash(`Export failed: ${(e as Error).message}`); }
  };

  const warnCount = result?.warnings.filter((w) => w.severity !== "info").length ?? 0;
  const busy = loading ? "true" : "false";

  return (
    <div className="app" data-view={view} onClick={() => menu && setMenu(null)}>
      <header className="topbar">
        <div className="brand"><span className="logo" aria-hidden>◇</span><div><h1>C CFG Analyzer</h1><span className="tag">control flow graphs · cyclomatic complexity</span></div></div>
        <nav className="top-actions" onClick={(e) => e.stopPropagation()}>
          <button className="btn" onClick={newAnalysis}>New analysis</button>
          <div className="menu-wrap">
            <button className="btn" aria-haspopup="menu" aria-expanded={menu === "examples"} onClick={() => setMenu(menu === "examples" ? null : "examples")}>Examples ▾</button>
            {menu === "examples" && (
              <div className="menu" role="menu" data-testid="examples-menu">
                {examples.length === 0 && <div className="menu-empty">Examples unavailable (backend not reachable).</div>}
                {examples.map((ex) => (
                  <button key={ex.id} role="menuitem" className="menu-item" onClick={() => loadExample(ex)}>
                    <span>{ex.title}</span><span className="m-chip">M = {ex.expected.course_complexity ?? ex.expected.complexity}</span>
                  </button>))}
              </div>)}
          </div>
          <button className="btn" onClick={() => setShowMethod(true)}>Methodology</button>
        </nav>
      </header>

      <div className="mobile-tabs" role="tablist">
        {(["code", "graph", "details"] as MobileView[]).map((v) => <button key={v} role="tab" aria-selected={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{v === "code" ? "Code" : v === "graph" ? "Graph" : "Details"}</button>)}
      </div>

      <main className={`workspace${graphExpanded ? " graph-expanded" : ""}`} aria-busy={busy}>
        {/* ---------------- left: editor ---------------- */}
        <section className="col col-code" aria-label="Source code">
          <div className="col-head">
            <h2>Source</h2>
            <div className="head-actions">
              <input ref={fileInput} type="file" accept=".c,.h,.txt,text/plain" hidden onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} data-testid="file-input" />
              <button className="btn" onClick={() => fileInput.current?.click()}>Upload .c</button>
              <button className="btn primary" onClick={() => run(source, result?.functions.find((f) => f.selected)?.name && !stale ? result.function.name : undefined)} disabled={loading || !source.trim()} data-testid="analyze">
                {loading ? <><span className="spinner" aria-hidden /> Analyzing…</> : "Analyze"}
              </button>
            </div>
          </div>
          <div className="editor-wrap">
            <CodeEditor value={source} onChange={setSource} marks={marks} onSelectLines={onSelectLines} onRun={() => run(source)} scrollToLine={scrollTo} />
          </div>
          <div className="col-foot">
            <label className="check-inline"><input type="checkbox" checked={mergeBlocks} onChange={(e) => { setMergeBlocks(e.target.checked); if (result && !stale) run(source, result.function.name, e.target.checked); }} /> Merge statements into basic blocks</label>
            <span className="muted small">Ctrl/⌘ + Enter to analyze</span>
          </div>
          {stale && <div className="banner stale" role="status">Source changed since the last analysis. The graph and highlights are out of date — press Analyze.</div>}
          {toast && <div className="banner danger" role="alert">{toast}</div>}
        </section>

        {/* ---------------- centre: graph ---------------- */}
        <section className="col col-graph" aria-label="Control flow graph">
          <div className="col-head">
            <h2>Control flow graph {result && <span className="fn-name mono">{result.function.name}()</span>}</h2>
            {result && (
              <div className="head-actions" onClick={(e) => e.stopPropagation()}>
                {result.functions.length > 1 && (
                  <label className="select-wrap">Function
                    <select value={result.function.name} onChange={(e) => run(analyzed ?? source, e.target.value)} data-testid="function-select" aria-label="Function to analyze">
                      {result.functions.map((f) => <option key={f.name} value={f.name} disabled={!!f.error}>{f.name}{f.complexity !== null ? ` (M=${f.complexity})` : ` — ${f.error}`}</option>)}
                    </select></label>)}
                <button className="btn" onClick={() => setDir(dir === "TB" ? "LR" : "TB")} title="Change layout direction">{dir === "TB" ? "↓ Top-down" : "→ Left-right"}</button>
                <button className="btn" onClick={() => setResetNonce((n) => n + 1)}>Reset layout</button>
                <button className="btn" onClick={() => setGraphExpanded((v) => !v)} aria-label={graphExpanded ? "Exit full screen graph" : "Show graph full screen"} title={graphExpanded ? "Exit full screen (Esc)" : "Show graph full screen"}>{graphExpanded ? "↙ Exit full screen" : "⛶ Full screen"}</button>
                <div className="menu-wrap">
                  <button className="btn" aria-haspopup="menu" onClick={() => setMenu(menu === "export" ? null : "export")}>Export ▾</button>
                  {menu === "export" && (
                    <div className="menu right" role="menu">
                      {([["svg", "Graph as SVG"], ["png", "Graph as PNG"], ["json", "Analysis as JSON"], ["md", "Summary (Markdown)"]] as const).map(([k, t]) =>
                        <button key={k} role="menuitem" className="menu-item" onClick={() => exportAs(k)} data-testid={`export-${k}`}>{t}</button>)}
                    </div>)}
                </div>
              </div>)}
          </div>

          <div className="graph-area">
            {loading && !result && <div className="state"><span className="spinner big" aria-hidden /><p>Analyzing…</p></div>}
            {error && !loading && (
              <div className="state error" role="alert" data-testid="error-state">
                <h3>{error.code === "SYNTAX_ERROR" ? "Syntax error" : error.code === "UNSUPPORTED_CONSTRUCT" ? "Unsupported construct" : "Analysis failed"}</h3>
                <p>{error.message}</p>
                {error.locations && error.locations.length > 0 && (
                  <ul className="locs">{error.locations.slice(0, 8).map((l, i) => <li key={i}><button className="link" onClick={() => jumpLine(l.line)}>line {l.line}, col {l.column}</button> {l.message}</li>)}</ul>)}
                {Array.isArray(error.details?.available) && <p className="small">Available functions: {(error.details!.available as string[]).join(", ")}</p>}
                <button className="btn" onClick={() => setView("code")}>Back to editor</button>
              </div>)}
            {!result && !error && !loading && <div className="state"><h3>No graph yet</h3><p>Paste C code or load an example, then press <strong>Analyze</strong>.</p></div>}
            {result && layout && (
              <div className={stale ? "graph-stale" : "graph-fresh"} style={{ height: "100%" }}>
                <CfgGraph result={result} layout={layout} dir={dir} selected={selected} pathNodes={pathNodes} pathEdges={pathEdges}
                  selectedEdge={selectedEdge} resetNonce={resetNonce} onSelectNode={onSelectNode} onSelectEdge={setSelectedEdge} />
              </div>)}
          </div>
          {result && <Legend />}
        </section>

        {/* ---------------- right: analysis ---------------- */}
        <aside className="col col-side" aria-label="Analysis">
          {result ? (
            <>
              <div className="tabs" role="tablist">
                {([["metrics", "Metrics"], ["node", "Node"], ["paths", `Paths (${result.paths.paths.length})`], ["warnings", `Warnings${warnCount ? ` (${warnCount})` : ""}`]] as [Tab, string][]).map(([k, t]) =>
                  <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)} data-testid={`tab-${k}`}>{t}</button>)}
              </div>
              <div className="tab-body">
                {tab === "metrics" && <MetricsPanel result={result} convention={convention} onConventionChange={(next) => {
                  setConvention(next);
                  run(source, result.function.name, mergeBlocks, next);
                }} />}
                {tab === "node" && (
                  <>
                    <NodeDetails result={result} node={selectedNode} onSelectNode={(id) => selectNodes([id])}
                      onShowShortest={(id) => { setPathIndex(null); setShortest(shortestPathTo(result, id)); }} onJumpLine={(l) => jumpLine(l)} />
                    {selected.size > 1 && <div className="panel-body"><h4>Also on the selected line(s)</h4><div className="chips">{[...selected].slice(1).map((id) => <button key={id} className="chip btn-chip" onClick={() => selectNodes([id])}>{id}</button>)}</div></div>}
                    {shortest && <div className="panel-body"><button className="btn small-btn" onClick={() => setShortest(null)}>Clear shortest-path highlight</button></div>}
                  </>)}
                {tab === "paths" && <PathsPanel result={result} selected={pathIndex} onSelect={(i) => { setShortest(null); setPathIndex(i); }} />}
                {tab === "warnings" && <WarningsPanel warnings={result.warnings} assumptions={result.assumptions} onJump={jumpLine} />}
              </div>
            </>
          ) : (
            <div className="state side-empty"><h3>Analysis</h3><p className="muted">Complexity, reachability, independent paths and warnings appear here after a successful analysis.</p></div>
          )}
        </aside>
      </main>
      {showMethod && <Methodology onClose={() => setShowMethod(false)} />}
    </div>
  );
}
