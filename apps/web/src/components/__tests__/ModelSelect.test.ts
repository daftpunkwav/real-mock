// @vitest-environment jsdom
/** ModelSelect: the empty option stays reachable with a default binding (null = follow default). */

import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import type { ModelProfile } from "@/types";
import { ModelSelect } from "../ModelSelect";

afterEach(() => cleanup());

function profile(id: number, label: string): ModelProfile {
  return {
    id,
    provider_id: 1,
    provider_name: "p",
    kind: "chat",
    model: `m${id}`,
    display_name: label,
    label,
    context_window: 8000,
    max_output: 2000,
    capabilities: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
    extras: {},
    enabled: true,
  };
}

const MODELS = [profile(1, "Whisper"), profile(2, "Edge")];
const [WHISPER] = MODELS as [ModelProfile, ModelProfile];

function setup(value: number | null, defaultProfile: ModelProfile | null, onChange = vi.fn()) {
  render(
    createElement(LocaleProvider, null, [
      createElement(ModelSelect, {
        key: "s",
        models: MODELS,
        value,
        onChange,
        ariaLabel: "STT",
        defaultProfile,
      }),
    ]),
  );
  return { onChange };
}

describe("ModelSelect", () => {
  // The test env defaults to the en locale.
  it("offers the default-following option even when a default profile exists", () => {
    setup(null, WHISPER);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText("Default (Whisper)")).toBeTruthy();
  });

  it("picking the empty option reports null", () => {
    const { onChange } = setup(2, WHISPER);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Default (Whisper)"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("shows Not-set style option when there is no default binding", () => {
    setup(null, null);
    fireEvent.click(screen.getByRole("combobox"));
    // Selected button + dropdown option both render it.
    expect(screen.getAllByText("Not set")).toHaveLength(2);
  });
});
