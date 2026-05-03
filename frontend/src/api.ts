import type { AnalysisResult, AnalyzeRequest, ApiOptions, ApiStatus } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://localhost:8000" : "");

export async function getStatus(): Promise<ApiStatus> {
  return fetchJson<ApiStatus>("/api/status");
}

export async function getOptions(): Promise<ApiOptions> {
  return fetchJson<ApiOptions>("/api/options");
}

export async function analyze(payload: AnalyzeRequest): Promise<AnalysisResult> {
  const result = await fetchJson<AnalysisResult>("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return normalizeAnalysisResult(result);
}

export function normalizeAnalysisResult(result: Partial<AnalysisResult>): AnalysisResult {
  return {
    answer: result.answer ?? "",
    confidence: result.confidence ?? "low",
    source_notice: result.source_notice ?? "",
    llm: result.llm ?? { provider: "template", model: "grounded-template", status: "fallback", warning: "" },
    required_features: result.required_features ?? [],
    recommended_tools: result.recommended_tools ?? [],
    comparison_table: result.comparison_table ?? [],
    review_themes: result.review_themes ?? [],
    evidence_snippets: result.evidence_snippets ?? [],
    ranking_explanation: result.ranking_explanation ?? [],
    risks: result.risks ?? [],
    follow_up_questions: result.follow_up_questions ?? [],
  };
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured for this deployment.");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}
