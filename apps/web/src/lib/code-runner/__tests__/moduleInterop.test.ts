/** TS export/require snippets end-to-end through the real worker driver.

The browser Worker is unavailable in Node, so this suite emulates it: the
unmodified `buildWorkerSource()` runs against a fake `self`, and snippets go
through the real sucrase transpile first — the same pipeline as the UI.
 */

import { describe, expect, it } from "vitest";

import { buildWorkerSource } from "../javascriptRunner";
import { transpileTypeScript } from "../typescriptRunner";

interface WorkerReply {
  ok: boolean;
  stdout: string;
  stderr: string;
  error?: string;
}

function makeFakeWorker() {
  const posted: WorkerReply[] = [];
  let handler: ((event: { data: unknown }) => unknown) | null = null;
  const selfShim = {
    set onmessage(fn: ((event: { data: unknown }) => unknown) | null) {
      handler = fn;
    },
    get onmessage() {
      return handler;
    },
    postMessage(msg: WorkerReply) {
      posted.push(msg);
    },
  };
  const grab = new Function("self", `${buildWorkerSource()}\nreturn self.onmessage;`);
  const onmessage = grab(selfShim) as (event: { data: unknown }) => unknown;
  return {
    async send(source: string): Promise<WorkerReply> {
      await onmessage({ data: { source } });
      const last = posted[posted.length - 1];
      if (!last) throw new Error("worker posted nothing");
      return last;
    },
  };
}

async function runTs(source: string): Promise<WorkerReply> {
  const outcome = await transpileTypeScript(source);
  if (!("code" in outcome)) throw new Error(`transpile failed: ${outcome.error}`);
  return makeFakeWorker().send(outcome.code);
}

const EXPORT_PRELUDE = [
  "export function bubbleSort<T>(arr: T[]): T[] {",
  "  const a = arr.slice();",
  "  return a.sort();",
  "}",
  "",
].join("\n");

describe("export/require interop", () => {
  it("runs exported functions invoked at top level", async () => {
    const reply = await runTs(`${EXPORT_PRELUDE}console.log(JSON.stringify(bubbleSort([3, 1, 2])));`);
    expect(reply.ok).toBe(true);
    expect(reply.stdout).toBe("[1,2,3]");
  });

  it("runs require.main self-tests (snippet is always the entry point)", async () => {
    const reply = await runTs(
      `${EXPORT_PRELUDE}if (typeof require !== "undefined" && require.main === module) {\n  console.log("selftest", JSON.stringify(bubbleSort([2, 1])));\n}`,
    );
    expect(reply.ok).toBe(true);
    expect(reply.stdout).toBe("selftest [1,2]");
    expect(reply.error ?? "").not.toMatch(/export|require/i);
  });

  it("rejects real module imports with a guidance error", async () => {
    const reply = await runTs('import fs from "fs";\nconsole.log(typeof fs);');
    expect(reply.ok).toBe(false);
    expect(reply.error ?? "").toMatch(/Cannot load module 'fs'/);
  });
});
