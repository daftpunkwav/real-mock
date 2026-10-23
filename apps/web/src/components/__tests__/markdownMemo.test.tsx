// @vitest-environment jsdom
/**
 * MarkdownContent must not re-parse an unchanged message when its parent
 * re-renders: the prep chat re-renders its message list on every
 * streamed-token flush, and re-parsing each settled bubble's markdown every
 * time burns the main thread for the whole reply.
 */

import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/** Counts how often the markdown pipeline runs (one run per render). */
let pipelineRuns = 0;

vi.mock("rehype-sanitize", async (importOriginal) => {
  const actual = await importOriginal<typeof import("rehype-sanitize")>();
  const sanitize = actual.default as unknown as (tree: unknown) => unknown;
  return {
    ...actual,
    default: (tree: unknown) => {
      pipelineRuns += 1;
      return sanitize(tree);
    },
  };
});

// The fenced-code chrome renders i18n labels; the test only needs the markup.
vi.mock("@/i18n", () => ({ useT: () => (key: string) => key }));

import { MarkdownContent } from "../MarkdownContent";

afterEach(() => {
  pipelineRuns = 0;
});

/** A parent that re-renders often (the streamed-token flush). */
function Host({ tick }: { tick: number }) {
  return (
    <div>
      <span data-testid="tick">{tick}</span>
      <MarkdownContent content="How should I design the order pipeline?" />
    </div>
  );
}

/** A reply whose fence never closes: code while streaming, prose once settled. */
const UNCLOSED_FENCE = [
  "Intro paragraph.",
  "",
  "```",
  "## Heading",
  "",
  "- item one",
  "- item two",
].join("\n");

describe("MarkdownContent", () => {
  it("does not re-parse the markdown when the parent re-renders", () => {
    const { rerender } = render(<Host tick={0} />);
    const afterFirstRender = pipelineRuns;
    expect(afterFirstRender).toBeGreaterThan(0);

    rerender(<Host tick={1} />);
    expect(pipelineRuns).toBe(afterFirstRender);

    rerender(<Host tick={2} />);
    expect(pipelineRuns).toBe(afterFirstRender);
  });

  it("re-parses the markdown when the content changes", () => {
    const { rerender } = render(<MarkdownContent content="first" />);
    const afterFirstRender = pipelineRuns;

    rerender(<MarkdownContent content="second" />);
    expect(pipelineRuns).toBeGreaterThan(afterFirstRender);
  });

  it("re-parses when the final flag flips, so the memo cannot swallow it", () => {
    const { container, rerender } = render(
      <MarkdownContent content={UNCLOSED_FENCE} final={false} />,
    );
    const afterFirstRender = pipelineRuns;
    // Streaming: the unclosed fence is a partial, so the tail stays code.
    expect(container.querySelector("h2")).toBeNull();

    rerender(<MarkdownContent content={UNCLOSED_FENCE} final={true} />);
    expect(pipelineRuns).toBeGreaterThan(afterFirstRender);
    // Settled: the fence is repaired, so the tail renders as prose again.
    expect(container.querySelector("h2")?.textContent).toBe("Heading");
  });
});
