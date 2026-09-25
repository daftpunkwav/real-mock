// @vitest-environment jsdom
/** Loading frames: primitives render decorative shimmer; variants keep a stable shell. */

import { createElement } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Skeleton, SkeletonText } from "../Skeleton";
import { PageSkeleton } from "../PageSkeleton";

afterEach(() => cleanup());

describe("Skeleton", () => {
  it("renders a decorative shimmer block", () => {
    const { container } = render(createElement(Skeleton, { className: "h-3 w-8" }));
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain("skeleton");
    expect(el.getAttribute("aria-hidden")).toBe("true");
  });

  it("renders one block per requested text line", () => {
    const { container } = render(createElement(SkeletonText, { lines: 4 }));
    expect(container.querySelectorAll(".skeleton")).toHaveLength(4);
  });
});

describe("PageSkeleton", () => {
  it("marks the region busy for every variant", () => {
    for (const variant of ["split", "board", "form", "stats", "rail-panel"] as const) {
      const { container, unmount } = render(
        createElement(PageSkeleton, { variant }),
      );
      const region = container.firstElementChild as HTMLElement;
      expect(region.getAttribute("role")).toBe("status");
      expect(region.getAttribute("aria-busy")).toBe("true");
      unmount();
    }
  });

  it("drops the header block when the real header renders above", () => {
    const { container } = render(
      createElement(PageSkeleton, { variant: "split", header: false }),
    );
    // header={false} keeps the body grid but no page-header skeleton.
    expect(container.querySelector(".page-header")).toBeNull();
    expect(container.firstElementChild?.className).toContain("page-shell");
  });

  it("omits the page-shell wrapper when the host page owns one", () => {
    const { container } = render(
      createElement(PageSkeleton, {
        variant: "split",
        header: false,
        shell: false,
      }),
    );
    expect(container.firstElementChild?.className).not.toContain("page-shell");
    expect(container.querySelectorAll(".surface-card").length).toBeGreaterThan(0);
  });
});
