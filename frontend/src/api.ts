import type { AnalysisResult, AnalyzeRequest, ApiOptions, ApiStatus } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://localhost:8000" : "same-origin");
const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

interface FetchRetryOptions {
  retries?: number;
  retryDelayMs?: number;
}

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
    enterprise_metadata: result.enterprise_metadata ?? [],
    vendor_metadata: result.vendor_metadata ?? [],
    open_source_alternatives: result.open_source_alternatives ?? [],
    ranking_explanation: result.ranking_explanation ?? [],
    risks: result.risks ?? [],
    follow_up_questions: result.follow_up_questions ?? [],
  };
}

export async function fetchJson<T>(path: string, init?: RequestInit, options: FetchRetryOptions = {}): Promise<T> {
  const url = apiUrl(path);
  const retries = options.retries ?? 2;
  const retryDelayMs = options.retryDelayMs ?? 450;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(url, init);
    } catch (err) {
      if (attempt < retries) {
        await delay(retryDelayMs * (attempt + 1));
        continue;
      }
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Could not reach the SaaSScout API at ${apiLabel()}. ${detail}. If Render is waking up, wait a moment and retry.`,
      );
    }

    if (response.ok) {
      return response.json() as Promise<T>;
    }

    const message = await response.text();
    if (RETRYABLE_STATUS_CODES.has(response.status) && attempt < retries) {
      await delay(retryDelayMs * (attempt + 1));
      continue;
    }
    throw new Error(message || `Request to ${url} failed with status ${response.status}`);
  }

  throw new Error(`Could not reach the SaaSScout API at ${apiLabel()}.`);
}

function delay(ms: number): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

function apiUrl(path: string): string {
  if (API_BASE_URL === "same-origin") return path;
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

function apiLabel(): string {
  return API_BASE_URL === "same-origin" ? "this site's /api proxy" : API_BASE_URL;
}
