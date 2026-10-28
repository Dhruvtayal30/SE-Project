import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";
import { memo } from "react";
import { pathFromPoints } from "../layout";

export interface EdgeData extends Record<string, unknown> {
  points: { x: number; y: number }[]; label: string; labelPos: { x: number; y: number } | null;
  expected: { sx: number; sy: number; tx: number; ty: number };
  back: boolean; reachable: boolean; onPath: boolean; selected: boolean; dim: boolean;
}

function CfgEdgeView({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps) {
  const d = data as EdgeData;
  // dagre's routed points are used while nodes sit where the layout put them; if a node was dragged, fall back to a Bézier.
  const moved = Math.abs(sourceX - d.expected.sx) > 12 || Math.abs(sourceY - d.expected.sy) > 12 ||
                Math.abs(targetX - d.expected.tx) > 12 || Math.abs(targetY - d.expected.ty) > 12;
  let path: string, lx: number | undefined, ly: number | undefined;
  if (moved || d.points.length < 2) {
    const [p, x, y] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
    path = p; lx = x; ly = y;
  } else { path = pathFromPoints(d.points); lx = d.labelPos?.x; ly = d.labelPos?.y; }
  const cls = ["cfg-edge", d.back ? "is-back" : "", d.reachable ? "" : "is-dead", d.onPath ? "is-path" : "", d.selected ? "is-selected" : "", d.dim ? "is-dim" : ""].join(" ");
  return (
    <>
      <BaseEdge id={id} path={path} className={cls} markerEnd={`url(#cfg-arrow${d.onPath ? "-hot" : d.back ? "-back" : ""})`} interactionWidth={14} />
      {d.label && lx !== undefined && ly !== undefined && (
        <EdgeLabelRenderer>
          <div className={`cfg-edge-label ${d.dim ? "is-dim" : ""} ${d.onPath ? "is-path" : ""}`} data-testid={`edge-label-${id}`}
               style={{ transform: `translate(-50%,-50%) translate(${lx}px,${ly}px)` }}>{d.label}</div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
export default memo(CfgEdgeView);
