import type { AnalysisResult, ApiError, ExampleItem } from "./types";

export class AnalysisFailure extends Error {
  constructor(public error: ApiError, public status: number) { super(error.message); }
}

async function parse(res: Response): Promise<any> {
  try { return await res.json(); }
  catch { throw new AnalysisFailure({ code: "BAD_RESPONSE", message: `The server returned an unreadable response (HTTP ${res.status}).` }, res.status); }
}

export async function analyze(
  source: string, opts: { fn?: string | null; mergeBlocks: boolean; convention?: "strict" | "course" }, signal?: AbortSignal,
): Promise<AnalysisResult> {
  const convention = opts.convention ?? "course";
  let res: Response;
  try {
    res = await fetch("/api/analyze", {
      method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, function: opts.fn || undefined, convention,
        options: { merge_blocks: opts.mergeBlocks } }),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new AnalysisFailure({ code: "NETWORK", message: "Cannot reach the analysis server. Is the backend running on port 5000?" }, 0);
  }
  const body = await parse(res);
  if (!res.ok || !body.ok) throw new AnalysisFailure(body.error ?? { code: "HTTP_ERROR", message: `HTTP ${res.status}` }, res.status);
  if (body.convention !== convention || body.complexity?.convention !== convention) {
    throw new AnalysisFailure({
      code: "CONVENTION_MISMATCH",
      message: `The analysis server did not apply the requested ${convention} convention. Restart the backend so it loads the updated analyzer.`,
    }, res.status);
  }
  return body as AnalysisResult;
}

export async function loadExamples(): Promise<ExampleItem[]> {
  const res = await fetch("/api/examples");
  const body = await parse(res);
  return body.examples ?? [];
}
