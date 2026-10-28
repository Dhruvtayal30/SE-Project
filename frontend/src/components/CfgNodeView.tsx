import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { CfgNode } from "../types";
import type { Direction } from "../layout";

export interface NodeData extends Record<string, unknown> {
  node: CfgNode; w: number; h: number; lines: string[]; dir: Direction;
  selected: boolean; onPath: boolean; dim: boolean;
}

function CfgNodeView({ data }: NodeProps) {
  const d = data as NodeData, n = d.node;
  const target = d.dir === "TB" ? Position.Top : Position.Left, source = d.dir === "TB" ? Position.Bottom : Position.Right;
  const cls = ["cfg-node", `k-${n.kind}`, d.selected ? "is-selected" : "", d.onPath ? "is-path" : "", d.dim ? "is-dim" : "",
    n.reachable ? "" : "is-dead", n.loop_header ? "is-loop" : "", n.returns ? "is-return" : ""].join(" ");
  const diamond = n.kind === "decision" || n.kind === "switch";
  return (
    <div className={cls} style={{ width: d.w, height: d.h }} data-node-id={n.id} data-kind={n.kind} data-testid={`node-${n.id}`}
         title={`${n.role}${n.reachable ? "" : " — unreachable"}`}>
      <Handle type="target" position={target} className="cfg-handle" isConnectable={false} />
      {diamond && (
        <svg className="cfg-shape" width={d.w} height={d.h} aria-hidden>
          <polygon points={`${d.w / 2},1.5 ${d.w - 1.5},${d.h / 2} ${d.w / 2},${d.h - 1.5} 1.5,${d.h / 2}`} />
          {n.kind === "switch" && <polygon className="inner" points={`${d.w / 2},7 ${d.w - 9},${d.h / 2} ${d.w / 2},${d.h - 7} 9,${d.h / 2}`} />}
        </svg>
      )}
      {n.kind !== "entry" && n.kind !== "exit" && <span className="cfg-index">n{n.index}</span>}
      <div className="cfg-text">{d.lines.map((l, i) => <div key={i}>{l}</div>)}</div>
      <Handle type="source" position={source} className="cfg-handle" isConnectable={false} />
    </div>
  );
}
export default memo(CfgNodeView);
