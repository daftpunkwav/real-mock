/** Diagram SVG helpers: error detection, sanitizing, fluid sizing. */

import { describe, expect, it } from "vitest";

import {
  fitDiagramSvg,
  isErrorDiagramSvg,
  repairMermaidSubgraphs,
  sanitizeDiagramSvg,
} from "../diagramSvg";

describe("isErrorDiagramSvg", () => {
  it("flags mermaid's error placeholder", () => {
    expect(isErrorDiagramSvg('<svg><g class="error-icon"/></svg>')).toBe(true);
    expect(isErrorDiagramSvg("<svg>Syntax error in text</svg>")).toBe(true);
  });

  it("passes real diagrams through", () => {
    expect(isErrorDiagramSvg('<svg viewBox="0 0 10 10"><g/></svg>')).toBe(false);
    expect(isErrorDiagramSvg("")).toBe(false);
  });

  it("ignores the .error-icon CSS rule shipped in every diagram stylesheet", () => {
    const healthy =
      '<svg id="a"><style>#a .error-icon{fill:#fff;}#a .error-text{fill:#000;}</style><g><rect/></g></svg>';
    expect(isErrorDiagramSvg(healthy)).toBe(false);
  });
});

describe("sanitizeDiagramSvg", () => {
  it("drops scripts and inline handlers, keeps shapes", () => {
    const dirty =
      '<svg onclick="evil()" width="10"><script>alert(1)</script><g onload=\'x\'><rect/></g></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("<script");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("onload");
    expect(clean).toContain("<rect");
  });
});

describe("fitDiagramSvg", () => {
  it("replaces fixed dimensions with fluid sizing", () => {
    const out = fitDiagramSvg('<svg width="640" height="480" viewBox="0 0 64 48"><g/></svg>');
    expect(out).toContain('width="100%"');
    expect(out).not.toMatch(/\sheight="/);
    expect(out).toContain("viewBox");
  });

  it("leaves non-svg input untouched", () => {
    expect(fitDiagramSvg("not svg")).toBe("not svg");
  });
});

describe("repairMermaidSubgraphs", () => {
  it("rewrites CJK subgraph headers to ascii ids with quoted titles", () => {
    const src = [
      "flowchart TB",
      '  subgraph 准备层 R["简历结构化档案"]',
      '    K["企业知识库 RAG"]',
      "  end",
      "  subgraph 工作流A[工作流 A：技术深挖]",
      '    A1["A1 开场暖场"]',
      "  end",
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSubgraphs(src)).toBe(
      [
        "flowchart TB",
        '  subgraph sg1["准备层 R 简历结构化档案"]',
        '    K["企业知识库 RAG"]',
        "  end",
        '  subgraph sg2["工作流A 工作流 A：技术深挖"]',
        '    A1["A1 开场暖场"]',
        "  end",
        '  subgraph sg3["收束"]',
        '    Z["结束"]',
        "  end",
      ].join("\n"),
    );
  });

  it("leaves valid subgraph headers untouched", () => {
    const src = 'flowchart TB\n  subgraph prep["准备层"]\n    K["x"]\n  end\n';
    expect(repairMermaidSubgraphs(src)).toBe(src);
  });

  it("ignores non-flowchart diagrams", () => {
    const src = "sequenceDiagram\n  A->>B: hi\n";
    expect(repairMermaidSubgraphs(src)).toBe(src);
  });
});
