/** capabilityConfig: form → zcode-style JSON projection, and Apply (JSON → form
 * fields + extras convention keys) with checkbox/capability-bit sync. */

import { describe, expect, it } from "vitest";

import {
  applyCapabilityConfig,
  capsConfigFromDraft,
} from "../capabilityConfig";
import { emptyDraft, type ModelDraft } from "../constants";

const draftWith = (over: Partial<ModelDraft>): ModelDraft => ({
  ...emptyDraft("chat"),
  ...over,
});

describe("capsConfigFromDraft", () => {
  it("derives modalities from capability checkboxes", () => {
    const view = capsConfigFromDraft(
      draftWith({
        capabilities: {
          chat: true,
          vision: true,
          audio_input: true,
          audio_output: true,
          reasoning: true,
        },
        context_window: "200000",
        max_output: "32000",
      }),
    );
    expect(view.modalities).toEqual({ input: ["text", "image", "audio"], output: ["text", "audio"] });
    expect(view.reasoning).toEqual({ enabled: true, variants: [], defaultVariant: "" });
    expect(view.limit).toEqual({ context: 200000, output: 32000 });
  });

  it("keeps checkbox-free modalities (video/pdf) from stored extras", () => {
    const draft = draftWith({
      extras_text: JSON.stringify({
        modalities: { input: ["text", "video", "pdf"], output: ["text"] },
      }),
    });
    expect(capsConfigFromDraft(draft).modalities.input).toEqual(["text", "video", "pdf"]);
  });

  it("drops a stored defaultVariant that is not in variants", () => {
    const draft = draftWith({
      extras_text: JSON.stringify({
        reasoning: { variants: ["low", "high"], defaultVariant: "bogus" },
      }),
    });
    expect(capsConfigFromDraft(draft).reasoning).toEqual({
      enabled: false,
      variants: ["low", "high"],
      defaultVariant: "",
    });
  });

  it("tolerates broken extras JSON", () => {
    expect(capsConfigFromDraft(draftWith({ extras_text: "{not json" })).modalities).toEqual({
      input: ["text"],
      output: ["text"],
    });
  });
});

describe("applyCapabilityConfig", () => {
  it("writes reasoning/modalities into form fields and extras", () => {
    const result = applyCapabilityConfig(
      JSON.stringify({
        reasoning: { enabled: true, variants: ["Low", "high", "high"], defaultVariant: "high" },
        limit: { context: 1000000, output: 128000 },
        modalities: { input: ["text", "image"], output: ["text"] },
      }),
      draftWith({ context_window: "1", max_output: "1" }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.capabilities).toEqual({
      chat: true,
      vision: true,
      audio_input: false,
      audio_output: false,
      reasoning: true,
    });
    expect(result.draft.context_window).toBe("1000000");
    expect(result.draft.max_output).toBe("128000");
    const extras = JSON.parse(result.draft.extras_text);
    expect(extras.reasoning).toEqual({ variants: ["low", "high"], defaultVariant: "high" });
    expect(extras.modalities).toEqual({ input: ["text", "image"], output: ["text"] });
  });

  it("drops a defaultVariant outside variants instead of failing", () => {
    const result = applyCapabilityConfig(
      JSON.stringify({ reasoning: { enabled: true, variants: ["low"], defaultVariant: "max" } }),
      draftWith({}),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(JSON.parse(result.draft.extras_text).reasoning).toEqual({ variants: ["low"] });
  });

  it("truncates over-long tokens to mirror the backend backstop", () => {
    const long = "v".repeat(40);
    const result = applyCapabilityConfig(
      JSON.stringify({ reasoning: { enabled: true, variants: [long], defaultVariant: long } }),
      draftWith({}),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(JSON.parse(result.draft.extras_text).reasoning).toEqual({
      variants: ["v".repeat(32)],
    });
  });

  it("preserves unrelated extras keys", () => {
    const draft = draftWith({
      extras_text: JSON.stringify({ tts_request: { voice_setting: { speed: 1.2 } } }),
    });
    const result = applyCapabilityConfig(
      JSON.stringify({ modalities: { input: ["text", "audio"], output: ["text", "audio"] } }),
      draft,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const extras = JSON.parse(result.draft.extras_text);
    expect(extras.tts_request).toEqual({ voice_setting: { speed: 1.2 } });
    expect(result.draft.capabilities.audio_input).toBe(true);
    expect(result.draft.capabilities.audio_output).toBe(true);
  });

  it("keeps current limit fields when the snippet omits them", () => {
    const result = applyCapabilityConfig(
      JSON.stringify({ reasoning: { enabled: true } }),
      draftWith({ context_window: "123", max_output: "456" }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.context_window).toBe("123");
    expect(result.draft.max_output).toBe("456");
  });

  it("rejects invalid JSON", () => {
    expect(applyCapabilityConfig("{nope", draftWith({})).ok).toBe(false);
    expect(applyCapabilityConfig("[1,2]", draftWith({})).ok).toBe(false);
  });

  it("round-trips through the view", () => {
    const start = draftWith({
      capabilities: { chat: true, vision: true, audio_input: false, audio_output: false, reasoning: true },
      context_window: "900000",
      max_output: "384000",
      extras_text: JSON.stringify({
        reasoning: { variants: ["off", "high", "max"], defaultVariant: "max" },
      }),
    });
    const once = applyCapabilityConfig(JSON.stringify(capsConfigFromDraft(start)), start);
    expect(once.ok).toBe(true);
    if (!once.ok) return;
    expect(JSON.parse(once.draft.extras_text)).toEqual({
      reasoning: { variants: ["off", "high", "max"], defaultVariant: "max" },
      modalities: { input: ["text", "image"], output: ["text"] },
    });
    expect(once.draft.capabilities).toEqual(start.capabilities);
  });
});
