import { Background, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow, useNodesState, type Edge, type Node } from "@xyflow/react";
import { useEffect, useMemo, useRef } from "react";
import type { Direction, Layout } from "../layout";
import type { AnalysisResult } from "../types";
import CfgEdgeView, { type EdgeData } from "./CfgEdgeView";
import CfgNodeView, { type NodeData } from "./CfgNodeView";

const nodeTypes = { cfg: CfgNodeView };
const edgeTypes = { cfg: CfgEdgeView };

interface Props {
  result: AnalysisResult; layout: Layout; dir: Direction;
  selected: Set<string>; pathNodes: Set<string>; pathEdges: Set<string>; selectedEdge: string | null;
  resetNonce: number; onSelectNode: (id: string | null) => void; onSelectEdge: (id: string | null) => void;
}

function Inner({ result, layout, dir, selected, pathNodes, pathEdges, selectedEdge, resetNonce, onSelectNode, onSelectEdge }: Props) {
  const rf = useReactFlow();
  const graphWrap = useRef<HTMLDivElement>(null);
  const pathActive = pathNodes.size > 0;

  // Trackpads emit wheel events for two-finger scrolling (and Ctrl/⌘+pinch).
  // Handle them directly so panning works in both the embedded and full-screen graph.
  useEffect(() => {
    const el = graphWrap.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        const { zoom } = rf.getViewport();
        void rf.zoomTo(Math.max(0.1, Math.min(2.5, zoom * Math.exp(-event.deltaY * 0.01))), { duration: 0 });
        return;
      }
      const scale = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? el.clientHeight : 1;
      const { x, y, zoom } = rf.getViewport();
      void rf.setViewport({ x: x - event.deltaX * scale, y: y - event.deltaY * scale, zoom }, { duration: 0 });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [rf]);

  const baseNodes = useMemo<Node[]>(() => result.graph.nodes.map((n) => {
    const b = layout.nodes[n.id];
    const data: NodeData = { node: n, w: b.w, h: b.h, lines: b.lines, dir, selected: false, onPath: false, dim: false };
    return { id: n.id, type: "cfg", position: { x: b.x, y: b.y }, data, width: b.w, height: b.h, draggable: true };
  }), [result, layout, dir]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(baseNodes);
  // Re-seed positions whenever the analysis/layout changes or the user presses "Reset layout".
  useEffect(() => { setNodes(baseNodes); setTimeout(() => rf.fitView({ padding: 0.15, duration: 250 }), 30); }, [baseNodes, resetNonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const shownNodes = useMemo(() => nodes.map((n) => {
    const base = n.data as NodeData;
    return { ...n, selected: selected.has(n.id), data: { ...base, selected: selected.has(n.id), onPath: pathNodes.has(n.id), dim: pathActive && !pathNodes.has(n.id) } };
  }), [nodes, selected, pathNodes, pathActive]);

  const edges = useMemo<Edge[]>(() => result.graph.edges.map((e) => {
    const sb = layout.nodes[e.source], tb = layout.nodes[e.target];
    const exp = dir === "TB" ? { sx: sb.x + sb.w / 2, sy: sb.y + sb.h, tx: tb.x + tb.w / 2, ty: tb.y } : { sx: sb.x + sb.w, sy: sb.y + sb.h / 2, tx: tb.x, ty: tb.y + tb.h / 2 };
    const touches = selected.has(e.source) || selected.has(e.target);
    const data: EdgeData = {
      points: layout.edges[e.id].points, label: e.label, labelPos: layout.edges[e.id].label, expected: exp,
      back: e.back_edge, reachable: e.reachable, onPath: pathEdges.has(e.id), selected: selectedEdge === e.id || (selected.size > 0 && touches),
      dim: (pathActive && !pathEdges.has(e.id)) || (!pathActive && selected.size > 0 && !touches && selectedEdge !== e.id),
    };
    return { id: e.id, source: e.source, target: e.target, type: "cfg", data, selectable: true };
  }), [result, layout, dir, selected, pathEdges, pathActive, selectedEdge]);

  useEffect(() => {
    const first = [...selected][0];
    if (first && selected.size === 1 && layout.nodes[first]) {
      const b = layout.nodes[first]; // keep the selection visible when it was chosen from the editor or a list
      const vp = rf.getViewport(); const el = document.querySelector(".graph-wrap") as HTMLElement | null;
      if (el) {
        const sx = (b.x + b.w / 2) * vp.zoom + vp.x, sy = (b.y + b.h / 2) * vp.zoom + vp.y;
        if (sx < 40 || sy < 40 || sx > el.clientWidth - 40 || sy > el.clientHeight - 40) rf.setCenter(b.x + b.w / 2, b.y + b.h / 2, { zoom: Math.max(vp.zoom, 0.8), duration: 300 });
      }
    }
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={graphWrap} className="graph-wrap" data-testid="graph">
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
        <defs>
          {[["", "var(--edge)"], ["-back", "var(--edge-back)"], ["-hot", "var(--accent)"]].map(([s, c]) => (
            <marker key={s} id={`cfg-arrow${s}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill={c} />
            </marker>
          ))}
        </defs>
      </svg>
      <ReactFlow nodes={shownNodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange}
        onNodeClick={(_, n) => { onSelectEdge(null); onSelectNode(n.id); }} onEdgeClick={(_, e) => onSelectEdge(e.id)}
        onPaneClick={() => { onSelectNode(null); onSelectEdge(null); }}
        panOnDrag zoomOnScroll={false} zoomOnPinch={false} minZoom={0.1} maxZoom={2.5} fitView fitViewOptions={{ padding: 0.15 }} nodesConnectable={false} elementsSelectable
        proOptions={{ hideAttribution: true }} deleteKeyCode={null}>
        <Background gap={22} size={1} />
        {result.graph.nodes.length > 25 && <MiniMap pannable zoomable nodeColor={(n) => ((n.data as NodeData).node.reachable ? "var(--minimap-node)" : "var(--border)")} />}
      </ReactFlow>
    </div>
  );
}

export default function CfgGraph(props: Props) {
  return <ReactFlowProvider><Inner {...props} /></ReactFlowProvider>;
}
