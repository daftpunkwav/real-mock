// @vitest-environment jsdom
/** PrepComposer input: multiline textarea, Enter-to-send, IME guard. */

import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { PrepComposer } from "../components/PrepComposer";

afterEach(() => cleanup());

function setup(overrides: Record<string, unknown> = {}) {
  const onSend = vi.fn();
  const onInputChange = vi.fn();
  const props = {
    messages: [],
    tokenUsage: 0,
    usage: null,
    contextBuckets: null,
    contextTotal: 0,
    estimatedPrompt: 0,
    chatModels: [],
    selectedModelId: null,
    onModelChange: vi.fn(),
    defaultChatProfile: null,
    effort: "medium" as const,
    onEffortChange: vi.fn(),
    loading: false,
    input: "hello",
    onInputChange,
    onSend,
    onStop: vi.fn(),
    onSlashCommand: vi.fn(),
    sessions: [],
    currentSessionId: null,
    pendingRefs: [],
    onAddRef: vi.fn(),
    onRemoveRef: vi.fn(),
    ...overrides,
  };
  render(
    createElement(LocaleProvider, {
      initialLocale: "zh-CN",
      children: createElement(PrepComposer, props),
    }),
  );
  // jsdom has no stored locale: the provider falls back to English strings.
  const box = screen.getByRole("textbox") as HTMLTextAreaElement;
  return { box, onSend, onInputChange };
}

describe("PrepComposer multiline input", () => {
  it("renders a two-row textarea (multiline/paste-safe), not a single-line input", () => {
    const { box } = setup();
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.getAttribute("title")).toMatch(/Shift\+Enter/);
    expect(box.getAttribute("rows")).toBe("2");
  });

  it("sends on Enter without Shift", () => {
    const { box, onSend } = setup();
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("does not send on Shift+Enter (newline instead)", () => {
    const { box, onSend } = setup();
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("does not send on IME composition Enter", () => {
    const { box, onSend } = setup();
    const event = new window.KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });    Object.defineProperty(event, "isComposing", { value: true });
    fireEvent(box, event);
    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows the effective context window next to the selected model", () => {
    const model = (id: number, provider: string, label: string, context_window: number) => ({
      id,
      provider_id: id,
      provider_name: provider,
      model: label,
      display_name: label,
      label,
      context_window,
      max_output: 8000,
      capabilities: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
      extras: {},
      enabled: true,
    });
    setup({
      chatModels: [
        model(1, "MiniMax", "MiniMax-M3", 1000000),
        model(2, "DeepSeek", "deepseek-chat", 128000),
      ],
      selectedModelId: 1,
    });
    // Window suffix makes a configured-vs-effective mismatch visible.
    const trigger = screen.getByRole("combobox", { name: /model/i });
    expect(trigger.textContent).toMatch(/MiniMax-M3/);
    expect(trigger.textContent).toMatch(/1M|100万/);
  });
});
