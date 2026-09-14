// @vitest-environment jsdom
/** DeepQaCard: knowledge brush-up and practice drills render when present. */

import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import type { TurnNote } from "@/types/domains/report";
import { DeepQaCard } from "../components/DeepQaCard";

afterEach(() => cleanup());

function setup(note: TurnNote) {
  render(createElement(LocaleProvider, null, [createElement(DeepQaCard, { key: "c", note })]));
}

const BASE: TurnNote = { turn_id: "t-0001", question: "What is a bloom filter?" };

describe("DeepQaCard", () => {
  it("renders brush-up and exercises when present", () => {
    setup({
      ...BASE,
      knowledge_brushup: "A bloom filter trades false positives for space.",
      exercises: ["List three cache-penetration fixes (direction: compare cost)."],
    });
    expect(screen.getByText(/Knowledge brush-up/)).toBeTruthy();
    expect(screen.getByText(/bloom filter trades/)).toBeTruthy();
    expect(screen.getByText(/Practice drills/)).toBeTruthy();
    expect(screen.getByText(/cache-penetration fixes/)).toBeTruthy();
  });

  it("omits brush-up and exercises sections when absent", () => {
    setup({ ...BASE });
    expect(screen.queryByText(/Knowledge brush-up/)).toBeNull();
    expect(screen.queryByText(/Practice drills/)).toBeNull();
  });
});
