import { describe, expect, it } from "vitest";

import {
  normalizeCnPunctuation,
  parseRewriteExample,
  tokenizeEvalText,
} from "../cnText";

describe("normalizeCnPunctuation", () => {
  it("converts half-width commas in CJK context", () => {
    expect(normalizeCnPunctuation("你好,世界")).toBe("你好，世界");
    expect(normalizeCnPunctuation("前端,后端")).toBe("前端，后端");
  });

  it("preserves punctuation between Latin words and numbers", () => {
    expect(normalizeCnPunctuation("a,b,c")).toBe("a,b,c");
    expect(normalizeCnPunctuation("React, Vue")).toBe("React, Vue");
  });

  it("converts periods, question marks, and colons in CJK context", () => {
    expect(normalizeCnPunctuation("完成了吗?")).toBe("完成了吗？");
    expect(normalizeCnPunctuation("注意:.env")).toBe("注意：.env");
    expect(normalizeCnPunctuation("很好.")).toBe("很好。");
  });

  it("converts parentheses and exclamation marks", () => {
    expect(normalizeCnPunctuation("(重要)")).toBe("（重要）");
    expect(normalizeCnPunctuation("太好了!")).toBe("太好了！");
  });

  it("returns empty and Latin-only input unchanged", () => {
    expect(normalizeCnPunctuation("")).toBe("");
    expect(normalizeCnPunctuation("abc")).toBe("abc");
  });
});

describe("parseRewriteExample", () => {
  it("parses object input", () => {
    expect(parseRewriteExample({ before: "A", after: "B" })).toEqual({
      before: "A",
      after: "B",
    });
  });

  it("parses JSON-like strings with single quotes and Python literals", () => {
    const raw = "{'before': '你好', 'after': '您好'}";
    expect(parseRewriteExample(raw)).toEqual({ before: "你好", after: "您好" });
  });

  it("parses legacy before and after labels", () => {
    expect(parseRewriteExample("【改前】旧文案 【改后】新文案")).toEqual({
      before: "旧文案",
      after: "新文案",
    });
  });

  it("parses arrow-separated input", () => {
    expect(parseRewriteExample("旧句子 → 新句子")).toEqual({
      before: "旧句子",
      after: "新句子",
    });
  });

  it("returns null for invalid input", () => {
    expect(parseRewriteExample(null)).toBeNull();
    expect(parseRewriteExample("")).toBeNull();
    expect(parseRewriteExample("无结构文本")).toBeNull();
  });
});

describe("tokenizeEvalText", () => {
  it("splits bold and code fragments", () => {
    const parts = tokenizeEvalText("提升 **QPS** 到 `100`");
    expect(parts).toContainEqual({ type: "bold", value: "QPS" });
    expect(parts).toContainEqual({ type: "code", value: "100" });
  });

  it("highlights metrics when markers are absent", () => {
    const parts = tokenizeEvalText("延迟 200ms，通过率 95%");
    expect(parts).toContainEqual({ type: "bold", value: "200ms" });
    expect(parts).toContainEqual({ type: "bold", value: "95%" });
  });

  it("returns an empty array for empty input", () => {
    expect(tokenizeEvalText("")).toEqual([]);
    expect(tokenizeEvalText(null as unknown as string)).toEqual([]);
  });
});
