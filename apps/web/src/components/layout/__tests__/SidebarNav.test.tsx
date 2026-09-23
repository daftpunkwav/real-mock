// @vitest-environment jsdom
/** SidebarNav: clicking an item highlights it immediately while the route is in flight. */

import type { MouseEvent, ReactNode } from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { NavContent } from "../SidebarNav";

const pathnameState = vi.hoisted(() => ({ current: "/" }));

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameState.current,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    onClick,
    ...rest
  }: {
    children: ReactNode;
    onClick?: (e: MouseEvent) => void;
    href: string;
  }) => (
    <a
      {...rest}
      onClick={(e) => {
        e.preventDefault();
        onClick?.(e);
      }}
    >
      {children}
    </a>
  ),
  useLinkStatus: () => ({ pending: false }),
}));

afterEach(() => {
  cleanup();
  pathnameState.current = "/";
});

function setup() {
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <NavContent collapsed={false} />
      </ThemeProvider>
    </LocaleProvider>,
  );
}

function navLink(container: HTMLElement, href: string): HTMLElement {
  const link = container.querySelector(`a[href="${href}"]`);
  if (!link) throw new Error(`missing nav link ${href}`);
  return link as HTMLElement;
}

describe("SidebarNav pending feedback", () => {
  it("marks the clicked item busy with a spinner before the pathname changes", () => {
    const { container } = setup();
    fireEvent.click(navLink(container, "/history"));
    expect(navLink(container, "/history").getAttribute("aria-busy")).toBe("true");
    expect(container.querySelector('[role="status"]')).toBeTruthy();
    // The previous page stays current until the navigation lands.
    expect(navLink(container, "/").getAttribute("aria-current")).toBe("page");
  });

  it("clears the pending mark once the target pathname renders", () => {
    const { container, rerender } = setup();
    fireEvent.click(navLink(container, "/history"));
    pathnameState.current = "/history";
    rerender(
      <LocaleProvider>
        <ThemeProvider>
          <NavContent collapsed={false} />
        </ThemeProvider>
      </LocaleProvider>,
    );
    expect(navLink(container, "/history").getAttribute("aria-current")).toBe("page");
    expect(navLink(container, "/history").getAttribute("aria-busy")).toBeNull();
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("does not mark clicks on the already-active route", () => {
    const { container } = setup();
    fireEvent.click(navLink(container, "/"));
    expect(navLink(container, "/").getAttribute("aria-busy")).toBeNull();
    expect(container.querySelector('[role="status"]')).toBeNull();
  });
});
