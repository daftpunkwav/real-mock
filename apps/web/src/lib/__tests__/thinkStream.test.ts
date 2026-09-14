import { describe, expect, it } from "vitest";

import { splitThinkAnswer, stripThinking, stripToolCallJson } from "../thinkStream";

describe("splitThinkAnswer", () => {
  it("extracts a complete think block", () => {
    const split = splitThinkAnswer("<think>先分析</think>正式回答");
    expect(split.thinking).toBe("先分析");
    expect(split.answer).toBe("正式回答");
    expect(split.hasThinking).toBe(true);
    expect(split.inThinking).toBe(false);
  });

  it("treats all content as the answer when no think block exists", () => {
    const split = splitThinkAnswer("正常回答内容");
    expect(split.answer).toBe("正常回答内容");
    expect(split.thinking).toBe("");
    expect(split.hasThinking).toBe(false);
  });

  it("preserves pending state for a tag split across tokens", () => {
    const split = splitThinkAnswer("答案前缀<think>未闭合思");
    // Content before the unclosed tag is the answer; the rest awaits the next token.
    expect(split.answer.startsWith("答案前缀")).toBe(true);
    expect(split.inThinking).toBe(true);
    expect(split.hasThinking).toBe(true);
  });

  it("supports the <thinking> tag variant", () => {
    const split = splitThinkAnswer("<thinking>双标签</thinking>回答");
    expect(split.thinking).toBe("双标签");
    expect(split.answer).toBe("回答");
  });

  it("supports fenced thinking blocks", () => {
    const split = splitThinkAnswer("```thinking\n代码思考\n```\n正文");
    expect(split.thinking).toContain("代码思考");
    expect(split.answer).toBe("正文");
  });

  it("trims thinking and leading answer whitespace", () => {
    const split = splitThinkAnswer("<think>   \n  思考  \n  </think>   回答");
    expect(split.thinking).toBe("思考");
    expect(split.answer).toBe("回答");
  });
});

describe("stripThinking", () => {
  it("removes thinking blocks and keeps the answer", () => {
    expect(stripThinking("<think>内部</think>外部")).toBe("外部");
  });
});

describe("stripToolCallJson", () => {
  it("removes a flat tool-call JSON fragment", () => {
    const text = '前文 {"tool": "github_search", "args": "x"} 后文';
    expect(stripToolCallJson(text)).not.toContain("github_search");
    expect(stripToolCallJson(text)).toContain("前文");
    expect(stripToolCallJson(text)).toContain("后文");
  });

  it("returns an empty input unchanged", () => {
    expect(stripToolCallJson("")).toBe("");
  });
});
