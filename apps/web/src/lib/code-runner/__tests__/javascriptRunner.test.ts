/** JavaScript runner: error formatting plus the no-Worker fallback contract. */

import { describe, expect, it } from "vitest";

import { buildWorkerSource, formatWorkerError, runJavascript } from "../javascriptRunner";

describe("formatWorkerError", () => {
  it("keeps name, message, and the first stack frames", () => {
    const err = new TypeError("boom");
    const text = formatWorkerError(err);
    expect(text).toContain("TypeError: boom");
  });

  it("redacts blob URLs and survives non-errors", () => {
    expect(formatWorkerError(null)).toBe("Unknown error");
    expect(formatWorkerError(undefined)).toBe("Unknown error");
    expect(formatWorkerError("plain")).toBe("plain");
    expect(formatWorkerError({ stack: "Error: x\n    at blob:https://a/b:1:1" })).toContain(
      "blob:…",
    );
  });
});

describe("buildWorkerSource", () => {
  it("assembles parseable worker code with the driver entry", () => {
    const source = buildWorkerSource();
    expect(() => new Function(source)).not.toThrow();
    expect(source).toContain("self.onmessage");
    expect(source).toContain("new Function");
    expect(source).toContain("postMessage");
  });
});

describe("runJavascript without a Worker", () => {
  it("settles as unavailable instead of throwing", async () => {
    // Node (and SSR) has no Web Worker; the UI hides the run button there.
    const result = await runJavascript("console.log(1)").done;
    expect(result.status).toBe("unavailable");
    expect(result.error).toBeTruthy();
  });
});
