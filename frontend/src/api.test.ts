import { describe, expect, it } from "vitest";
import { normalizeAnalysisResult } from "./api";

describe("normalizeAnalysisResult", () => {
  it("fills missing arrays and LLM state", () => {
    const result = normalizeAnalysisResult({ answer: "Direct answer" });

    expect(result.answer).toBe("Direct answer");
    expect(result.recommended_tools).toEqual([]);
    expect(result.comparison_table).toEqual([]);
    expect(result.llm.provider).toBe("template");
  });
});
