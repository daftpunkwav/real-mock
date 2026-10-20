// @vitest-environment jsdom
/**
 * MarkdownContent must not re-parse an unchanged message when its parent
 * re-renders: the prep chat re-renders the whole message list on every
 * streamed-token flush, and re-parsing every settled message's markdown each
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
});
