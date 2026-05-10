import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson, getBootstrap, normalizeAnalysisResult } from "./api";

afterEach(() => {
  vi.useRealTimers();
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
  it("loads bootstrap with a short no-retry request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      ready: false,
      warming: true,
      error: "",
      message: "Preparing",
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBootstrap()).resolves.toEqual({
      ready: false,
      warming: true,
      error: "",
      message: "Preparing",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/bootstrap"), expect.objectContaining({
      signal: expect.any(AbortSignal),
    }));
  });

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

  it("adds a wake-up hint after exhausted transient HTTP retries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 504 })));

    await expect(fetchJson("/api/status", undefined, { retries: 0, retryDelayMs: 0 })).rejects.toThrow(
      /Render is waking up/,
    );
  });

  it("aborts requests that exceed the configured startup timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      })),
    );

    const request = expect(fetchJson("/api/bootstrap", undefined, { retries: 0, timeoutMs: 25 })).rejects.toThrow(
      /Request timed out after 25ms/,
    );
    await vi.advanceTimersByTimeAsync(25);

    await request;
    vi.useRealTimers();
  });
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
