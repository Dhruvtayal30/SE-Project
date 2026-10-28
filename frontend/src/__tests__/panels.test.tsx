import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MetricsPanel from "../components/MetricsPanel";
import NodeDetails from "../components/NodeDetails";
import PathsPanel from "../components/PathsPanel";
import WarningsPanel from "../components/WarningsPanel";
import { deadResult, infiniteResult, loopResult, switchResult } from "./helpers";

describe("MetricsPanel", () => {
  it("shows exactly the backend's values", () => {
    render(<MetricsPanel result={switchResult} />);
    expect(screen.getByTestId("m-value").textContent).toBe("8");
    expect(screen.getByTestId("formula").textContent).toContain("M = 23 − 17 + 2×1 = 8");
    expect(screen.getByTestId("formula").textContent).toContain("M = 7 + 1 = 8");
    expect(screen.getByTestId("formula").textContent).toContain("M = P_d + 1");
  });
  it("shows grouped backend predicates and requests the selected convention", () => {
    const r = structuredClone(switchResult);
    r.convention = "course";
    r.complexity.convention = "course";
    r.complexity.convention_label = "Course convention";
    r.complexity.predicate_count = 8;
    r.complexity.predicate_value = 9;
    r.complexity.predicate_substituted = "M = 8 + 1 = 9";
    r.complexity.predicate_breakdown = { if: 1, for: 1, while: 0, do_while: 0, logical: 2, ternary: 0, case: 3, default: 1 };
    const onConventionChange = vi.fn();
    render(<MetricsPanel result={r} convention="course" onConventionChange={onConventionChange} />);
    expect(screen.getByTestId("predicate-list").textContent).toContain("default: 1");
    expect(screen.getByTestId("formula").textContent).toContain("M = 8 + 1 = 9");
    const toggle = screen.getByLabelText(/Count `default` as a decision/);
    expect((toggle as HTMLInputElement).checked).toBe(true);
    fireEvent.click(toggle);
    expect(onConventionChange).toHaveBeenCalledWith("strict");
  });
  it("never recalculates: a changed API value is displayed as given", () => {
    const r = structuredClone(switchResult);
    r.complexity.value = 99;
    render(<MetricsPanel result={r} />);
    expect(screen.getByTestId("m-value").textContent).toBe("99");
  });
  it("flags the non-terminating case and the formula disagreement", () => {
    render(<MetricsPanel result={infiniteResult} />);
    expect(screen.getByTestId("metrics-panel").textContent).toMatch(/EXIT is not reachable/);
    expect(screen.getByText(/no reachable EXIT/)).toBeTruthy();
  });
  it("mentions unreachable nodes excluded from M", () => {
    render(<MetricsPanel result={deadResult} />);
    expect(screen.getByTestId("metrics-panel").textContent).toMatch(/excluded from M/);
  });
});

describe("PathsPanel", () => {
  it("lists one card per basis path and reports selection", () => {
    const onSelect = vi.fn();
    render(<PathsPanel result={loopResult} selected={null} onSelect={onSelect} />);
    expect(screen.getAllByTestId(/^path-\d+$/)).toHaveLength(loopResult.paths.paths.length);
    fireEvent.click(screen.getByTestId("path-2"));
    expect(onSelect).toHaveBeenCalledWith(2);
  });
  it("explains when no terminating basis exists instead of inventing paths", () => {
    render(<PathsPanel result={infiniteResult} selected={null} onSelect={() => {}} />);
    expect(screen.getByTestId("paths-unavailable").textContent).toMatch(/not reachable/i);
    expect(screen.queryAllByTestId(/^path-\d+$/)).toHaveLength(0);
  });
});

describe("NodeDetails", () => {
  it("asks for a selection when nothing is selected", () => {
    render(<NodeDetails result={loopResult} node={null} onSelectNode={() => {}} onShowShortest={() => {}} onJumpLine={() => {}} />);
    expect(screen.getByTestId("node-empty")).toBeTruthy();
  });
  it("shows role, statements and in/out edges of a decision", () => {
    const node = loopResult.graph.nodes.find((n) => n.kind === "decision" && n.construct === "for")!;
    const onSelect = vi.fn();
    render(<NodeDetails result={loopResult} node={node} onSelectNode={onSelect} onShowShortest={() => {}} onJumpLine={() => {}} />);
    const box = within(screen.getByTestId("node-details"));
    expect(box.getByText(/Decision \(for-loop condition\)/)).toBeTruthy();
    expect(box.getByText(/Incoming \(2\)/)).toBeTruthy();   // from the init block and from the loop-back edge
    expect(box.getByText(/Outgoing \(2\)/)).toBeTruthy();
    expect(box.getByText("loop back edge")).toBeTruthy();
    expect(box.getByText("i < n")).toBeTruthy();
  });
  it("marks unreachable nodes", () => {
    const node = deadResult.graph.nodes.find((n) => !n.reachable && n.kind === "block")!;
    render(<NodeDetails result={deadResult} node={node} onSelectNode={() => {}} onShowShortest={() => {}} onJumpLine={() => {}} />);
    expect(screen.getByTestId("node-details").textContent).toMatch(/Unreachable/);
  });
});

describe("WarningsPanel", () => {
  it("lists warnings with severity text (not colour alone) and line links", () => {
    const onJump = vi.fn();
    render(<WarningsPanel warnings={deadResult.warnings} assumptions={deadResult.assumptions} onJump={onJump} />);
    expect(screen.getAllByText(/Warning/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByText(/^line \d+$/)[0]);
    expect(onJump).toHaveBeenCalled();
  });
});
