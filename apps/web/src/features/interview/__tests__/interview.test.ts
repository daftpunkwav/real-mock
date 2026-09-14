import { describe, expect, it } from "vitest";

import { isLikelyEchoOfAssistant, normalizeEchoText } from "../echo";
import { toVisibleChatMessages } from "../messages";
import { planStepTitle } from "../processes";

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

describe("planStepTitle", () => {
  const plan = [
    { round_no: 1, kind: "tech_1", workflow_type: "technical", label: "Tech 1", focus: "baseline", pass_criteria: "answer basics" },
    { round_no: 2, kind: "hr_1", workflow_type: "hr", label: "HR 1", focus: "motivation", pass_criteria: "" },
  ];
  it("joins focus and pass criteria", () => {
    expect(planStepTitle(plan, 1)).toBe("baseline\nanswer basics");
  });
  it("falls back to focus alone without a pass bar", () => {
    expect(planStepTitle(plan, 2)).toBe("motivation");
  });
  it("returns empty for unknown rounds", () => {
    expect(planStepTitle(plan, 9)).toBe("");
    expect(planStepTitle(undefined, 1)).toBe("");
  });
});
