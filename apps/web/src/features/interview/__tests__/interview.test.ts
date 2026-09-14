import { describe, expect, it } from "vitest";

import { isLikelyEchoOfAssistant, normalizeEchoText } from "../echo";
import { toVisibleChatMessages } from "../messages";

describe("echo", () => {
  it("normalizeEchoText strips punctuation and whitespace", () => {
    expect(normalizeEchoText("你好，世界！")).toBe("你好世界");
  });

  it("detects highly similar echo of assistant text", () => {
    const asst = "请先做一下自我介绍，包括项目经历";
    expect(isLikelyEchoOfAssistant("请先做一下自我介绍，包括项目经历", asst)).toBe(true);
    expect(isLikelyEchoOfAssistant("我做过支付对账", asst)).toBe(false);
  });
});

describe("toVisibleChatMessages", () => {
  it("filters system roles and empty content", () => {
    expect(
      toVisibleChatMessages([
        { role: "system", content: "prompt" },
        { role: "assistant", content: "开场" },
        { role: "user", content: "  " },
        { role: "user", content: "你好" },
      ]),
    ).toEqual([
      { role: "assistant", content: "开场" },
      { role: "user", content: "你好" },
    ]);
  });
});
