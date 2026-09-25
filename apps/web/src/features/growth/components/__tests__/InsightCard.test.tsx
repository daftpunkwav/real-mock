// @vitest-environment jsdom
/**
 * @file InsightCard.test.tsx
 * @description Render-branch tests for the AI growth-insight card: loading /
 * generating / empty / ready states, including the refresh callback wiring.
 */

import type { ReactNode } from "react";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InsightCard } from "../InsightCard";
import type { GrowthInsight } from "@/lib/api/clients";

vi.mock("@/i18n", () => ({
  useT: () => (key: string, values?: Record<string, unknown>) =>
    values && "count" in values ? `${key}:${values.count}` : key,
}));

vi.mock("./Section", () => ({
  // The real Section pulls layout styles; the card logic under test is the state.
  Section: ({
    title,
    action,
    children,
  }: {
    title: string;
    action?: ReactNode;
    children?: ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      {action}
      {children}
    </section>
  ),
}));

function makeInsight(overrides: Partial<GrowthInsight> = {}): GrowthInsight {
  return {
    headline: "steady rise",
    trajectory: "scores improved across sessions",
    trajectory_stage: "rising",
    recurring_weaknesses: [{ skill: "sql", count: 3, trend: "improving", advice: "drill plans" }],
    improving_areas: ["system design"],
    resume_gap_insights: ["add metrics"],
    training_plan: [{ area: "algorithms", based_on: "session 3", actions: ["daily practice"] }],
    generated_at: null,
    session_count: 4,
    locale: "zh-CN",
    ...overrides,
  };
}

describe("InsightCard", () => {
  afterEach(cleanup);

  it("renders the loading and generating spin states", () => {
    render(<InsightCard insight={null} status="loading" onRefresh={() => {}} />);
    expect(screen.getByText("insight.loading")).toBeTruthy();

    // Re-render as generating in a fresh tree.
    render(<InsightCard insight={null} status="generating" onRefresh={() => {}} />);
    expect(screen.getByText("insight.generating")).toBeTruthy();
  });

  it("renders the empty guide with a generate button", () => {
    const onRefresh = vi.fn();
    render(<InsightCard insight={null} status="empty" onRefresh={onRefresh} />);
    expect(screen.getByText("insight.empty")).toBeTruthy();
    fireEvent.click(screen.getByText("insight.generate"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders the full ready state and wires the refresh action", () => {
    const onRefresh = vi.fn();
    render(<InsightCard insight={makeInsight()} status="ready" onRefresh={onRefresh} />);

    expect(screen.getByText("steady rise")).toBeTruthy();
    expect(screen.getByText("scores improved across sessions")).toBeTruthy();
    expect(screen.getByText("sql")).toBeTruthy();
    expect(
      screen.getByText(
        (_content, element) =>
          element?.textContent === "insight.appearedIn:3 · insight.trend.improving",
      ),
    ).toBeTruthy();
    expect(screen.getByText("system design")).toBeTruthy();
    expect(screen.getByText("add metrics")).toBeTruthy();
    expect(screen.getByText("algorithms")).toBeTruthy();
    expect(screen.getByText("daily practice")).toBeTruthy();
    expect(screen.getByText("insight.basedOn:4")).toBeTruthy();

    fireEvent.click(screen.getByText("insight.refresh"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("keeps rendering when the payload is a degraded empty shell", () => {
    const degraded = makeInsight({
      headline: "",
      recurring_weaknesses: [],
      improving_areas: [],
      resume_gap_insights: [],
      training_plan: [],
    });
    render(<InsightCard insight={degraded} status="ready" onRefresh={() => {}} />);
    expect(screen.getByText("scores improved across sessions")).toBeTruthy();
    expect(screen.queryByText("insight.patterns")).toBeNull();
  });
});
