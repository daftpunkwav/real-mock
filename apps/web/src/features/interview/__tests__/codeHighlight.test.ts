import { describe, expect, it } from "vitest";

import { highlightCode } from "../codeHighlight";

describe("highlightCode", () => {
  it("escapes HTML specials so injected markup cannot break the overlay", () => {
    const out = highlightCode('x = "<script>"', "python");
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;script&gt;");
  });

  it("colors python keywords, strings, comments, and def function names", () => {
    const out = highlightCode(
      "# hi\ndef reverse_list(head):\n    return None\n    s = \"abc\"\n",
      "python",
    );
    expect(out).toContain('class="tok-com"');
    expect(out).toContain('class="tok-kw"'); // def / return
    expect(out).toContain('class="tok-fn"'); // reverse_list after def
    expect(out).toContain('class="tok-str"'); // "abc" and None? None is keyword
    // the def name itself must not also be a keyword span
    expect(out).toMatch(/tok-fn">reverse_list</);
  });

  it("keeps triple-quoted strings in one string span", () => {
    const out = highlightCode('doc = """a\nb"""\n', "python");
    const spans = out.match(/tok-str/g);
    expect(spans && spans.length >= 1).toBe(true);
    expect(out).toContain("a\nb"); // newline preserved for the pre overlay
  });

  it("colors javascript template strings and line comments", () => {
    const out = highlightCode("// note\nconst s = `hi ${x}`;\n", "javascript");
    expect(out).toContain('class="tok-com"');
    expect(out).toContain('class="tok-str"');
    expect(out).toMatch(/tok-kw">const</);
  });

  it("numbers get the number token", () => {
    const out = highlightCode("x = 42\n", "python");
    expect(out).toMatch(/tok-num">42</);
  });
});
