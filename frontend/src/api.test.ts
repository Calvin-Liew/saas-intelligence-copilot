import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson, normalizeAnalysisResult } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("normalizeAnalysisResult", () => {
  it("fills missing arrays and LLM state", () => {
    const result = normalizeAnalysisResult({ answer: "Direct answer" });

    expect(result.answer).toBe("Direct answer");
    expect(result.recommended_tools).toEqual([]);
    expect(result.comparison_table).toEqual([]);
    expect(result.enterprise_metadata).toEqual([]);
    expect(result.vendor_metadata).toEqual([]);
    expect(result.open_source_alternatives).toEqual([]);
    expect(result.llm.provider).toBe("template");
  });
});

describe("fetchJson", () => {
  it("retries transient network failures", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchJson<{ status: string }>("/api/status", undefined, { retries: 1, retryDelayMs: 0 })).resolves.toEqual({
      status: "ok",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries temporary HTTP failures", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("API is starting", { status: 503 }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchJson<{ status: string }>("/api/status", undefined, { retries: 1, retryDelayMs: 0 })).resolves.toEqual({
      status: "ok",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("returns an actionable message after exhausted network retries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(fetchJson("/api/status", undefined, { retries: 0, retryDelayMs: 0 })).rejects.toThrow(
      /Could not reach the SaaSScout API/,
    );
  });
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
