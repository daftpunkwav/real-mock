/** Mermaid source repairs: packed headers, subgraph ids, preamble scan. */

import { describe, expect, it } from "vitest";

import {
  repairMermaidFlowHeader,
  repairMermaidSource,
  repairMermaidSubgraphs,
} from "../diagramSource";

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

  it("leaves direction-only headers and non-flowcharts alone", () => {
    expect(repairMermaidFlowHeader("flowchart TB\n")).toBe("flowchart TB\n");
    expect(repairMermaidFlowHeader("sequenceDiagram\n  A->>B: hi")).toBe(
      "sequenceDiagram\n  A->>B: hi",
    );
  });

  it("repairs a packed header on a CRLF source and keeps the CRLF line endings", () => {
    const src = 'flowchart TB A["a"] --> B["b"]\r\nB --> C["c"]\r\n';
    expect(repairMermaidFlowHeader(src)).toBe(
      'flowchart TB\r\nA["a"] --> B["b"]\r\nB --> C["c"]\r\n',
    );
  });

  it("repairs a packed header that follows a preamble, preserving the preamble", () => {
    const cases = [
      {
        src: '%%{init: {"theme":"dark"}}%%\nflowchart TD A["a"] --> B["b"]',
        expected: '%%{init: {"theme":"dark"}}%%\nflowchart TD\nA["a"] --> B["b"]',
      },
      {
        src: '%% prep chart\nflowchart TD A["a"] --> B["b"]',
        expected: '%% prep chart\nflowchart TD\nA["a"] --> B["b"]',
      },
      {
        src: '---\ntitle: "t"\n---\nflowchart TD A["a"] --> B["b"]',
        expected: '---\ntitle: "t"\n---\nflowchart TD\nA["a"] --> B["b"]',
      },
      {
        src: '\n\nflowchart TD A["a"] --> B["b"]',
        expected: '\n\nflowchart TD\nA["a"] --> B["b"]',
      },
      {
        src: '%% prep chart\n---\ntitle: "t"\n---\nflowchart TD A["a"] --> B["b"]',
        expected: '%% prep chart\n---\ntitle: "t"\n---\nflowchart TD\nA["a"] --> B["b"]',
      },
    ];
    for (const { src, expected } of cases) {
      expect(repairMermaidFlowHeader(src)).toBe(expected);
    }
  });

  it("does not reach past the declaration into the body of another diagram", () => {
    const src = "%% c\nsequenceDiagram\n  Note over A: graph LR is only prose here";
    expect(repairMermaidFlowHeader(src)).toBe(src);
    const unterminated = '---\ntitle: "t"\nflowchart TD A["a"] --> B["b"]';
    expect(repairMermaidFlowHeader(unterminated)).toBe(unterminated);
    const unclosedDirective = '%%{init: {"a":1}\nflowchart TD A["a"] --> B["b"]';
    expect(repairMermaidFlowHeader(unclosedDirective)).toBe(unclosedDirective);
  });

  it("skips a multi-line directive, whose interior lines are not a declaration", () => {
    const src = ["%%{init: {", '  "theme": "dark"', "}}%%", 'flowchart TD A["a"] --> B["b"]'].join(
      "\n",
    );
    expect(repairMermaidFlowHeader(src)).toBe(
      ["%%{init: {", '  "theme": "dark"', "}}%%", "flowchart TD", 'A["a"] --> B["b"]'].join("\n"),
    );
  });

  it("keeps frontmatter open across an indented YAML block-scalar fence", () => {
    // mermaid closes the block on a `---` at the opening indent only, so an
    // indented `---` belonging to `title: |` is scalar content.
    const src = [
      "---",
      "title: |",
      "  ---",
      "  body",
      "---",
      'flowchart TD A["a"] --> B["b"]',
    ].join("\n");
    expect(repairMermaidFlowHeader(src)).toBe(
      ["---", "title: |", "  ---", "  body", "---", "flowchart TD", 'A["a"] --> B["b"]'].join("\n"),
    );
  });
});

describe("repairMermaidSource", () => {
  it("repairs a CJK subgraph packed onto the header line", () => {
    const src = [
      'flowchart TD subgraph 准备层 R["简历结构化档案"]',
      '    A["开场"] --> B["收束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSource(src)).toBe(
      [
        "flowchart TD",
        'subgraph sg1["准备层 R 简历结构化档案"]',
        '    A["开场"] --> B["收束"]',
        "  end",
      ].join("\n"),
    );
  });

  it("still repairs an unpacked chart exactly as before", () => {
    const src = ["flowchart TB", "  subgraph 收束", '    Z["结束"]', "  end"].join("\n");
    expect(repairMermaidSource(src)).toBe(
      ["flowchart TB", '  subgraph sg1["收束"]', '    Z["结束"]', "  end"].join("\n"),
    );
  });

  it("returns the source untouched when neither repair applies", () => {
    const src = "sequenceDiagram\n  A->>B: hi\n";
    expect(repairMermaidSource(src)).toBe(src);
  });

  it("rewrites a CJK subgraph when a preamble precedes the declaration", () => {
    const cases = [
      '%%{init: {"theme":"dark"}}%%\n',
      "%% prep chart\n",
      '---\ntitle: "t"\n---\n',
      "\n",
    ];
    for (const preamble of cases) {
      const src = `${preamble}flowchart TD\n  subgraph 收束\n    Z["结束"]\n  end`;
      expect(repairMermaidSource(src)).toBe(
        `${preamble}flowchart TD\n  subgraph sg1["收束"]\n    Z["结束"]\n  end`,
      );
    }
  });

  it("rewrites both a packed header and a CJK subgraph behind a preamble", () => {
    const src = [
      '%%{init: {"theme":"dark"}}%%',
      'flowchart TD A["开场"]',
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSource(src)).toBe(
      [
        '%%{init: {"theme":"dark"}}%%',
        "flowchart TD",
        'A["开场"]',
        '  subgraph sg1["收束"]',
        '    Z["结束"]',
        "  end",
      ].join("\n"),
    );
  });

  it("rewrites a CJK subgraph behind a multi-line directive", () => {
    const src = [
      "%%{init: {",
      '  "theme": "dark"',
      "}}%%",
      'flowchart TD A["开场"]',
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSource(src)).toBe(
      [
        "%%{init: {",
        '  "theme": "dark"',
        "}}%%",
        "flowchart TD",
        'A["开场"]',
        '  subgraph sg1["收束"]',
        '    Z["结束"]',
        "  end",
      ].join("\n"),
    );
  });

  it("leaves the frontmatter alone, including subgraph-like scalar content", () => {
    // The block scalar holds a line that looks like a subgraph header; it is
    // YAML metadata and must keep its wording (and its numbering).
    const src = [
      "---",
      "title: |",
      "  subgraph 收束",
      "---",
      "flowchart TD",
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSource(src)).toBe(
      [
        "---",
        "title: |",
        "  subgraph 收束",
        "---",
        "flowchart TD",
        '  subgraph sg1["收束"]',
        '    Z["结束"]',
        "  end",
      ].join("\n"),
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

  it("leaves a header with no id or title untouched", () => {
    // Nothing follows the keyword, so there is no header to rewrite: the
    // source must come back whole for the caller's no-op guard to hold.
    const src = ["flowchart TB", "  subgraph ", '    K["x"]', "  end"].join("\n");
    expect(repairMermaidSubgraphs(src)).toBe(src);
    const spaced = ["flowchart TB", "  subgraph   ", '    K["x"]', "  end"].join("\n");
    expect(repairMermaidSubgraphs(spaced)).toBe(spaced);
    expect(repairMermaidSource(spaced)).toBe(spaced);
  });

  it("ignores non-flowchart diagrams", () => {
    const src = "sequenceDiagram\n  A->>B: hi\n";
    expect(repairMermaidSubgraphs(src)).toBe(src);
  });

  it("skips ids the chart already binds to a node", () => {
    const src = [
      "flowchart TB",
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
      '  sg1["已有节点"] --> Z["结束"]',
    ].join("\n");
    expect(repairMermaidSubgraphs(src)).toBe(
      [
        "flowchart TB",
        '  subgraph sg2["收束"]',
        '    Z["结束"]',
        "  end",
        '  sg1["已有节点"] --> Z["结束"]',
      ].join("\n"),
    );
  });

  it("skips ids the chart already binds to a valid subgraph", () => {
    const src = [
      "flowchart TB",
      "  subgraph 准备层",
      '    A["a"]',
      "  end",
      '  subgraph sg2["已有子图"]',
      '    B["b"]',
      "  end",
      "  subgraph 收束",
      '    Z["结束"]',
      "  end",
    ].join("\n");
    expect(repairMermaidSubgraphs(src)).toBe(
      [
        "flowchart TB",
        '  subgraph sg1["准备层"]',
        '    A["a"]',
        "  end",
        '  subgraph sg2["已有子图"]',
        '    B["b"]',
        "  end",
        '  subgraph sg3["收束"]',
        '    Z["结束"]',
        "  end",
      ].join("\n"),
    );
  });
});
