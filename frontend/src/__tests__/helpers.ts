import type { AnalysisResult } from "../types";
import sw from "./fixtures/15_switch_and_conditions.json";
import loop from "./fixtures/06_for_continue.json";
import inf from "./fixtures/14_infinite_loop.json";
import dead from "./fixtures/13_unreachable.json";

export const switchResult = sw as unknown as AnalysisResult;
export const loopResult = loop as unknown as AnalysisResult;
export const infiniteResult = inf as unknown as AnalysisResult;
export const deadResult = dead as unknown as AnalysisResult;
