/** markdownComponents: table styling hooks and plain-fence block chrome. */

import type { ReactElement, ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { CodeBlock } from "../CodeBlock";
import { markdownComponents } from "../markdownComponents";

type CodeProps = { className?: string; children?: ReactNode };
type WrapProps = { children?: ReactNode };

function renderCode(props: CodeProps): ReactNode {
  const fn = markdownComponents.code as unknown as (p: CodeProps) => ReactNode;
  return fn(props);
}

function classOf(node: ReactNode): string {
  return (node as ReactElement<{ className?: string }>).props.className ?? "";
}

describe("code", () => {
  it("renders fenced python as a CodeBlock", () => {
    const el = renderCode({ className: "language-python", children: "print(1)\n" });
    expect((el as ReactElement).type).toBe(CodeBlock);
    expect((el as ReactElement<{ language?: string }>).props.language).toBe("python");
  });

  it("renders a plain multiline fence as a chromed block, not an inline pill", () => {
    const el = renderCode({ children: "line one\nline two\n" });
    expect((el as ReactElement).type).toBe(CodeBlock);
    expect((el as ReactElement<{ language?: string }>).props.language).toBeUndefined();
  });

  it("keeps single-line plain code inline", () => {
    const el = renderCode({ children: "npm install" });
    expect((el as ReactElement).type).toBe("code");
  });
});

describe("table", () => {
  it("wraps tables in a scroll container with tabular numerals", () => {
    const fn = markdownComponents.table as unknown as (p: WrapProps) => ReactNode;
    const el = fn({}) as ReactElement<WrapProps>;
    expect(el.type).toBe("div");
    expect(classOf(el)).toContain("overflow-x-auto");
    const table = (el.props as WrapProps).children as ReactNode;
    expect(classOf(table)).toContain("tabular-nums");
  });

  it("wraps cell prose at word boundaries and stripes rows", () => {
    const td = markdownComponents.td as unknown as (p: WrapProps) => ReactNode;
    // break-word (not anywhere): prose wraps normally, and inline code keeps
    // whole identifiers ("resume_overview") intact — the table scrolls instead.
    expect(classOf(td({}))).toContain("[overflow-wrap:break-word]");
    expect(classOf(td({}))).not.toContain("[overflow-wrap:anywhere]");
    const tr = markdownComponents.tr as unknown as (p: WrapProps) => ReactNode;
    // Zebra keeps the faint fill; hover takes the deeper muted tone.
    expect(classOf(tr({}))).toContain("even:bg-surface-alt");
    expect(classOf(tr({}))).toContain("hover:bg-surface-muted");
  });

  it("keeps inline code from breaking mid-token", () => {
    const el = renderCode({ children: "resume_overview" });
    expect(classOf(el)).toContain("whitespace-nowrap");
  });

  it("renders a distinct header surface (not background-alt) for contrast", () => {
    // Regression: the header fill used background-alt, which is near-identical
    // to the white message bubble, so the header read as a plain body row.
    const thead = markdownComponents.thead as unknown as (p: WrapProps) => ReactNode;
    expect(classOf(thead({}))).toContain("bg-surface-muted");
    const th = markdownComponents.th as unknown as (p: WrapProps) => ReactNode;
    expect(classOf(th({}))).toContain("font-semibold");
  });
});
