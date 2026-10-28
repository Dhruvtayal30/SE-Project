export default function Methodology({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Methodology" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row-between"><h2>Methodology</h2><button className="btn" onClick={onClose}>Close</button></div>
        <h3>Pipeline</h3>
        <p className="small">C source → tree-sitter syntax tree → fine-grained CFG (frontier algorithm) → basic-block merging → reachability, dominators and loops → cyclomatic complexity → independent basis paths → JSON. The program is parsed, never compiled or run.</p>
        <h3>Cyclomatic complexity</h3>
        <p className="small"><code>M = E − N + 2P</code> on the part of the graph reachable from ENTRY. It is cross-checked with <code>M = 1 + Σ max(0, outdeg(v) − 1)</code> and with an independent decision count taken from the syntax tree. Every <code>if</code>, loop condition, <code>case</code> label, <code>&amp;&amp;</code>, <code>||</code> and <code>?:</code> adds one; <code>default</code> and <code>else</code> add nothing.</p>
        <h3>Conventions</h3>
        <ul className="small bullets">
          <li><code>&amp;&amp;</code>, <code>||</code>, <code>!</code> and <code>?:</code> are expanded into separate decisions in evaluation order.</li>
          <li>Literal-true loops (<code>while (1)</code>, <code>for (;;)</code>) have no False edge. Other constants are not folded.</li>
          <li>Unreachable code stays in the graph (dashed) but is excluded from M.</li>
          <li>If EXIT is unreachable the two formulas differ by one and no basis paths are produced.</li>
          <li>Basis paths are structural: conditions are not solved.</li>
        </ul>
        <h3>Not supported</h3>
        <p className="small">Macro expansion, <code>#if</code> inside functions, GNU statement expressions, nested functions, computed goto, and inter-procedural analysis. These are reported, not ignored.</p>
      </div>
    </div>
  );
}
