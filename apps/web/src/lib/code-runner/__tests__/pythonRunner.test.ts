/** Python runner: skulpt error shaping (engine I/O stays in the browser). */

import { describe, expect, it } from "vitest";

import { formatSkulptError, runPython } from "../pythonRunner";

describe("formatSkulptError", () => {
  it("prefers the skulpt type name plus first arg", () => {
    expect(
      formatSkulptError({ tp$name: "NameError", args: { v: [{ v: "name 'x' is not defined" }] } }),
    ).toBe("NameError: name 'x' is not defined");
  });

  it("falls back through Error, message, and unknown shapes", () => {
    expect(formatSkulptError(new RangeError("bad"))).toBe("RangeError: bad");
    expect(formatSkulptError({ tp$name: "SyntaxError" })).toBe("SyntaxError");
    expect(formatSkulptError(null)).toBe("Unknown error");
    expect(formatSkulptError(42)).toBe("Error");
  });
});

describe("runPython empty input", () => {
  it("short-circuits without loading the engine", async () => {
    const result = await runPython("  \n ").done;
    expect(result).toMatchObject({ status: "ok", output: "" });
  });
});
