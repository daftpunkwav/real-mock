/** Pure ask_user dialog helpers: normalization defaults and answer text. */

import { describe, expect, it } from "vitest";

import { formatAskAnswer, normalizeAskDialog } from "@/lib/askDialog";

describe("normalizeAskDialog", () => {
  it("defaults legacy events to single options with free text", () => {
    expect(normalizeAskDialog({ question: "Q?", options: ["a", "b"] })).toEqual({
      question: "Q?",
      options: ["a", "b"],
      selection: "single",
      widget: "options",
      scale: undefined,
      allow_custom: true,
      suggested: null,
    });
  });

  it("passes the recommended choice through, blank becomes null", () => {
    expect(
      normalizeAskDialog({ question: "Q?", options: ["a", "b"], suggested: "b" }).suggested,
    ).toBe("b");
    expect(
      normalizeAskDialog({ question: "Q?", options: ["a", "b"], suggested: "" }).suggested,
    ).toBeNull();
  });

  it("keeps multi/slider/rating shapes and caps options at 8", () => {
    const dialog = normalizeAskDialog({
      question: "Q?",
      options: Array.from({ length: 10 }, (_, i) => `o${i}`),
      selection: "multi",
      widget: "slider",
      scale: { min: 0, max: 10, step: 2, unit: "h" },
      allow_custom: false,
    });
    expect(dialog.selection).toBe("multi");
    expect(dialog.widget).toBe("slider");
    expect(dialog.scale).toEqual({ min: 0, max: 10, step: 2, unit: "h" });
    expect(dialog.options).toHaveLength(8);
    expect(dialog.allow_custom).toBe(false);
  });

  it("drops duplicate labels to keep dialog keys unique", () => {
    expect(
      normalizeAskDialog({ question: "Q?", options: ["a", "b", "a", " a "] }).options,
    ).toEqual(["a", "b"]);
  });

  it("falls back on unknown selection/widget and drops non-numeric scale", () => {
    const dialog = normalizeAskDialog({
      question: "Q?",
      options: ["a", "b"],
      selection: "whatever",
      widget: "carousel",
      scale: { min: "x" },
    });
    expect(dialog.selection).toBe("single");
    expect(dialog.widget).toBe("options");
    expect(dialog.scale).toBeUndefined();
  });

  it("degrades an unusable slider to options, mirroring the backend", () => {
    expect(
      normalizeAskDialog({ question: "Q?", options: ["a", "b"], widget: "slider", scale: null }).widget,
    ).toBe("options");
    expect(
      normalizeAskDialog({
        question: "Q?",
        options: ["a", "b"],
        widget: "slider",
        scale: { min: 5, max: 5 },
      }).widget,
    ).toBe("options");
  });

  it("parses allow_custom like the backend (only explicit negatives off)", () => {
    expect(normalizeAskDialog({ question: "Q?", options: [] }).allow_custom).toBe(true);
    expect(normalizeAskDialog({ question: "Q?", options: [], allow_custom: "false" }).allow_custom).toBe(false);
    expect(normalizeAskDialog({ question: "Q?", options: [], allow_custom: 0 }).allow_custom).toBe(false);
  });
});

describe("formatAskAnswer", () => {
  it("joins multi selections with 、", () => {
    expect(
      formatAskAnswer({ widget: "options" }, { options: ["A", "B", "C"] }),
    ).toBe("A、B、C");
  });

  it("formats slider values with unit and trims .0", () => {
    expect(
      formatAskAnswer({ widget: "slider", scale: { unit: "小时" } }, { slider: "7.0" }),
    ).toBe("7小时");
    expect(
      formatAskAnswer({ widget: "slider", scale: { step: 0.5 } }, { slider: "7.5" }),
    ).toBe("7.5");
  });

  it("formats ratings as value/max", () => {
    expect(
      formatAskAnswer({ widget: "rating", scale: { max: 5 } }, { rating: 4 }),
    ).toBe("4/5");
  });
});

describe("normalizeAskDialog: multi-question dialogs", () => {
  const multi = {
    question: "Q1?",
    options: ["a", "b"],
    questions: [
      { question: "Q1?", options: ["a", "b"] },
      { question: "Q2?", widget: "slider", scale: { min: 1, max: 40 } },
      { question: "Q3?", widget: "rating" },
    ],
  };

  it("attaches normalized questions when several survive", () => {
    const dialog = normalizeAskDialog(multi);
    // Flat fields mirror the first question.
    expect(dialog.question).toBe("Q1?");
    expect(dialog.questions).toHaveLength(3);
    expect(dialog.questions?.[1]).toMatchObject({ question: "Q2?", widget: "slider" });
    expect(dialog.questions?.[1]?.selection).toBe("single");
    expect(dialog.questions?.[2]?.widget).toBe("rating");
  });

  it("keeps the flat shape when only one question is present", () => {
    const dialog = normalizeAskDialog({ ...multi, questions: [multi.questions[0]] });
    expect(dialog.questions).toBeUndefined();
  });

  it("caps the questions array at 8 and drops junk entries", () => {
    const dialog = normalizeAskDialog({
      ...multi,
      questions: [
        ...Array.from({ length: 10 }, (_, i) => ({ question: `Q${i}?`, options: ["a", "b"] })),
        "junk",
        null,
      ],
    });
    expect(dialog.questions).toHaveLength(8);
    expect(dialog.questions?.[7]?.question).toBe("Q7?");
  });
});
