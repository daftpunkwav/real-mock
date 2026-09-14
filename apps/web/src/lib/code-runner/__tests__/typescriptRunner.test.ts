/** TypeScript runner: type-stripping plus delegation failure contracts. */

import { describe, expect, it } from "vitest";

import { runTypeScript, transpileTypeScript } from "../typescriptRunner";

describe("transpileTypeScript", () => {
  it("strips type annotations into runnable JavaScript", async () => {
    const outcome = await transpileTypeScript(
      "const x: number = 1;\nconsole.log(x + 1);",
    );
    expect("code" in outcome && outcome.code).toContain("console.log(x + 1)");
    expect("code" in outcome && outcome.code).not.toContain(": number");
  });

  it("lowers ESM export/import to CJS for the new-Function worker", async () => {
    const outcome = await transpileTypeScript(
      'import { x } from "./y";\nexport function f(a: number): number {\n  return a + x;\n}\nexport default f;\n',
    );
    if (!("code" in outcome)) throw new Error(`unexpected error: ${outcome.error}`);
    expect(outcome.code).not.toMatch(/(^|\n)\s*(import|export)\s/m);
    expect(outcome.code).toContain("exports.");
  });

  it("reports syntax errors as data, not throws", async () => {
    const outcome = await transpileTypeScript("const x: = ;;;");
    expect("error" in outcome && outcome.error).toMatch(/parse failed/i);
  });

  it("passes empty input through", async () => {
    expect(await transpileTypeScript("  \n ")).toEqual({ code: "" });
  });
});

describe("runTypeScript", () => {
  it("maps transpile failures to error results", async () => {
    const result = await runTypeScript("const x: = ;;;").done;
    expect(result.status).toBe("error");
    expect(result.error).toMatch(/parse failed/i);
  });

  it("settles as unavailable where workers are missing", async () => {
    const result = await runTypeScript("console.log(1 as number)").done;
    expect(result.status).toBe("unavailable");
  });
});
