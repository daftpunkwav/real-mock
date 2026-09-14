/** repairUnclosedFence: reclaim markdown swallowed by a stray open fence. */

import { describe, expect, it } from "vitest";

import { normalizeLooseTables, repairUnclosedFence } from "../MarkdownContent";

const SWALLOWED = [
  "Intro paragraph stays.",
  "",
  "```",
  "## What I'll do",
  "",
  "---",
  "",
  "- **I'm pausing the active coaching.**",
  "- **No tools called, no note written**",
  "",
  "## Your next move",
  "",
  "1. Refresh the tab",
  "2. Re-send the audit request",
  "",
  "| Turn | What you sent |",
  "|---|---|",
  "| T1 | short question |",
  "| T2 | another one |",
].join("\n");

describe("repairUnclosedFence", () => {
  it("drops the stray opener and returns the markdown tail", () => {
    const out = repairUnclosedFence(SWALLOWED);
    expect(out).not.toContain("```");
    expect(out).toContain("## What I'll do");
    expect(out).toContain("## Your next move");
    expect(out).toContain("| Turn | What you sent |");
    expect(out).toContain("Intro paragraph stays.");
  });

  it("recovers tables end-to-end through the normalizer", () => {
    const out = normalizeLooseTables(repairUnclosedFence(SWALLOWED));
    expect(out).toContain("| Turn | What you sent |");
    expect(out).toContain("| --- | --- |");
  });

  it("drops a bare language tag without leaking it as text", () => {
    const src = ["Some intro.", "", "```text", "## Head", "", "- item one", "- item two"].join(
      "\n",
    );
    const out = repairUnclosedFence(src);
    expect(out).not.toContain("```text");
    expect(out).not.toMatch(/^text$/m);
    expect(out).toContain("## Head");
  });

  it("keeps trailing prose on a glued opener line", () => {
    const src = [
      "## Section",
      "",
      "``` please read below",
      "## Head",
      "",
      "- item one",
      "- item two",
    ].join("\n");
    const out = repairUnclosedFence(src);
    expect(out).toContain("please read below");
    expect(out).toContain("## Head");
  });

  it("leaves genuine code tails alone (single structure kind)", () => {
    const src = [
      "Here is the script:",
      "",
      "```python",
      "## section one",
      "x = a | b",
      "## section two",
      "y = compute(x)",
      "print(y)",
    ].join("\n");
    expect(repairUnclosedFence(src)).toBe(src);
  });

  it("leaves pipe-heavy code tails alone (P0-1 protection holds)", () => {
    const src = [
      "```python",
      "a = x | y",
      "b = p | q",
      "c = m | n",
      "print(a, b, c)",
    ].join("\n");
    expect(repairUnclosedFence(src)).toBe(src);
  });

  it("leaves short tails alone", () => {
    const src = ["Intro.", "", "```", "## Lonely head"].join("\n");
    expect(repairUnclosedFence(src)).toBe(src);
  });

  it("leaves closed fences and plain prose untouched", () => {
    const closed = ["Text.", "", "```js", "console.log(1);", "```", "", "More."].join("\n");
    expect(repairUnclosedFence(closed)).toBe(closed);
    expect(repairUnclosedFence("Just **prose** here.")).toBe("Just **prose** here.");
    expect(repairUnclosedFence("")).toBe("");
  });
});
