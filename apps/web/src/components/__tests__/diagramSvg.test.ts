/** Diagram SVG helpers: error detection, sanitizing, fluid sizing. */

import { describe, expect, it } from "vitest";

import {
  fitDiagramSvg,
  isErrorDiagramSvg,
  repairMermaidFlowHeader,
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

  it("drops active embeds and javascript/data URLs, keeps safe links", () => {
    const dirty =
      '<svg><foreignObject><body>hi</body></foreignObject><embed src="x"/><a href="javascript:alert(1)">b</a><a href="https://example.com">ok</a></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("foreignObject");
    expect(clean).not.toContain("<embed");
    expect(clean).not.toContain("javascript:");
    expect(clean).toContain("https://example.com");
  });

  it("drops script blocks whose closing tag carries attributes", () => {
    const dirty = '<svg><script src="x">alert(1)</script foo="bar"><rect/></svg>';
    expect(sanitizeDiagramSvg(dirty)).toBe("<svg><rect/></svg>");
  });

  it("removes spliced tags after nested-block removal until stable", () => {
    const dirty = "<svg><scr<script></script>ipt>alert(1)</scr</script>ipt></svg>";
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean.toLowerCase()).not.toContain("<script");
    expect(clean).not.toContain("alert(1)</scr");
  });

  it("strips unclosed active tags and leftover script bodies", () => {
    const dirty = '<svg><script src="x">alert(1)<rect/></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean.toLowerCase()).not.toContain("<script");
    expect(clean).toContain("<rect");
  });

  it("strips inline handlers glued to a slash separator", () => {
    const dirty = '<svg><img src="x"/onload=alert(1)><rect/></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("onload");
    expect(clean).toContain("<rect");
  });

  it("escapes stray active-tag openings without a closing bracket", () => {
    const dirty = "<svg><text>x</text><script";
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("<script");
    expect(clean).toContain("&lt;script");
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

describe("repairMermaidFlowHeader", () => {
  it("splits the direction from the first node packed on the header line", () => {
    const src = 'flowchart TB A1["a"] --> B1["b"]\nB1 --> C1["c"]';
    expect(repairMermaidFlowHeader(src)).toBe('flowchart TB\nA1["a"] --> B1["b"]\nB1 --> C1["c"]');
  });

  it("repairs the CJK chart that mermaid rejected with a NODE_STRING error", () => {
    const src = [
      'flowchart TB A1["◎ 指标定义<br/>Recall@k到底怎么算,分母是什么"] --> B1["◎ 评测集<br/>多少条、哪来的、谁标的"]',
      'B1 --> C1["◎ 基线<br/>优化前同一套集上的分数"]',
    ].join("\n");
    const [header, node, ...rest] = repairMermaidFlowHeader(src).split("\n");
    expect(header).toBe("flowchart TB");
    expect(node).toBe(
      'A1["◎ 指标定义<br/>Recall@k到底怎么算,分母是什么"] --> B1["◎ 评测集<br/>多少条、哪来的、谁标的"]',
    );
    expect(rest).toEqual(['B1 --> C1["◎ 基线<br/>优化前同一套集上的分数"]']);
  });

  it("handles every direction keyword and the graph alias", () => {
    for (const keyword of [
      "flowchart TB",
      "flowchart TD",
      "flowchart BT",
      "flowchart RL",
      "graph LR",
    ]) {
      expect(repairMermaidFlowHeader(`${keyword} A["a"] --> B["b"]`)).toBe(
        `${keyword}\nA["a"] --> B["b"]`,
      );
    }
  });

  it("leaves an already correct multi-line header untouched", () => {
    const src = 'flowchart TB\n  A1["a"] --> B1["b"]\n  B1 --> C1["c"]';
    expect(repairMermaidFlowHeader(src)).toBe(src);
  });

  it("is idempotent", () => {
    const once = repairMermaidFlowHeader('graph LR A["a"] --> B["b"]');
    expect(repairMermaidFlowHeader(once)).toBe(once);
  });

  it("leaves direction-only headers, non-flowcharts, and CRLF input alone", () => {
    expect(repairMermaidFlowHeader("flowchart TB\n")).toBe("flowchart TB\n");
    expect(repairMermaidFlowHeader("sequenceDiagram\n  A->>B: hi")).toBe(
      "sequenceDiagram\n  A->>B: hi",
    );
    expect(repairMermaidFlowHeader('flowchart TB A["a"]\r\nB --> C')).toBe(
      'flowchart TB A["a"]\r\nB --> C',
    );
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
