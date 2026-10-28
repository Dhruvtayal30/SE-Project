// Mirrors the JSON returned by POST /api/analyze (docs/API.md). The backend is the single source of
// truth: the frontend only displays these values and never recomputes graph metrics.

export type NodeKind = "entry" | "exit" | "block" | "decision" | "switch";

export interface Stmt { text: string; line: number; column: number; end_line: number; end_column: number }

export interface CfgNode {
  id: string; index: number; kind: NodeKind; construct: string; role: string; explanation: string;
  label: string; statements: Stmt[]; lines: number[];
  reachable: boolean; can_reach_exit: boolean; distance: number | null; parent_edge: string | null;
  loop_header: boolean; in_degree: number; out_degree: number; returns: boolean;
}

export interface CfgEdge {
  id: string; index: number; source: string; target: string; kind: string; label: string;
  via: string | null; back_edge: boolean; reachable: boolean;
}

export interface Applicability { code: string; message: string }

export interface Complexity {
  value: number; convention: "strict" | "course"; convention_label: string; formula: string; substituted: string;
  nodes: number; edges: number; components: number; decision_nodes: number; branch_contribution: number;
  branch_formula: string; branch_substituted: string; branch_value: number;
  predicate_formula: string; predicate_substituted: string; predicate_count: number;
  predicate_breakdown: Record<string, number>; predicate_value: number; formulas_agree: boolean;
  structural: { value: number; decisions: number; breakdown: Record<string, number>; agrees: boolean; scope: string };
  full_graph: { nodes: number; edges: number; components: number; value: number };
  interpretation: { band: string; label: string; text: string };
  applicability: Applicability[];
}

export interface BasisPath {
  index: number; nodes: string[]; edges: string[]; length: number; repeats_nodes: boolean;
  new_edges: string[]; decisions: { node: string; edge: string; label: string }[];
}

export interface Paths {
  status: "complete" | "partial" | "unavailable" | "skipped" | "disabled";
  reason?: string; convention?: string; expected: number; rank: number; paths: BasisPath[];
}

export interface Warning {
  code: string; severity: "info" | "warning" | "error"; message: string;
  line: number | null; column: number | null; node?: string | null;
}

export interface FunctionItem {
  name: string; start_line: number; end_line: number; complexity: number | null; error: string | null;
  selected: boolean; default: boolean;
}

export interface AnalysisResult {
  ok: true; api_version: string; convention: "strict" | "course";
  function: { name: string; signature: string; start_line: number; end_line: number };
  functions: FunctionItem[];
  graph: { entry: string; exit: string; nodes: CfgNode[]; edges: CfgEdge[] };
  statistics: {
    nodes_total: number; edges_total: number; nodes_reachable: number; nodes_unreachable: number;
    decision_nodes: number; switch_nodes: number; basic_blocks: number; loops: number; function_lines: number;
  };
  complexity: Complexity;
  reachability: {
    exit_reachable: boolean; unreachable_nodes: string[]; trapped_nodes: string[]; back_edges: string[];
    irreducible: boolean; reachable_percent: number;
  };
  paths: Paths;
  warnings: Warning[];
  source_map: { line_to_nodes: Record<string, string[]> };
  assumptions: string[];
}

export interface ErrorLocation { line: number; column: number; message: string }
export interface ApiError { code: string; message: string; locations?: ErrorLocation[]; details?: Record<string, unknown> }

export interface ExampleItem {
  id: string; title: string; description: string; file: string; function: string; source: string;
  expected: { nodes: number; edges: number; reachable_nodes: number; complexity: number; decision_nodes: number;
              course_complexity?: number; exit_reachable: boolean; basis_status: string };
}
