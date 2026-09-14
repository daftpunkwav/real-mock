/**
 * @file types.ts
 * @description Public contracts for fenced-code execution. Runners implement
 * CodeRunner; UI code depends only on these types plus the registry, never on
 * engine internals (Worker, transpilers, interpreters).
 */

/** Terminal outcome of one execution. */
export type ExecutionStatus =
  | "ok"
  | "error"
  | "timeout"
  | "cancelled"
  | "unavailable";

/** Result of one execution: captured output plus a machine-readable status. */
export interface ExecutionResult {
  status: ExecutionStatus;
  /** Captured stdout (and stderr merged where the engine cannot separate). */
  output: string;
  /** Captured stderr when the engine separates streams; else undefined. */
  stderr?: string;
  /** Human-readable failure detail; present unless status is "ok". */
  error?: string;
  /** Wall-clock time in milliseconds. */
  durationMs: number;
  /** True when output was cut at the configured cap. */
  truncated: boolean;
}

/** Per-run resource limits; runners fall back to the defaults below. */
export interface RunLimits {
  /** Hard wall-clock budget; the runner must settle by roughly this time. */
  timeoutMs?: number;
  /** Maximum captured output characters before truncation. */
  maxOutputChars?: number;
}

/** Handle for an in-flight execution. done always settles (never rejects). */
export interface ExecutionHandle {
  done: Promise<ExecutionResult>;
  cancel(): void;
}

/** Execution engine for one language family. */
export interface CodeRunner {
  readonly id: string;
  run(source: string, limits?: RunLimits): ExecutionHandle;
}

/** Default wall-clock budget per run (engines enforce their own bound too). */
export const DEFAULT_TIMEOUT_MS = 10000;

/** Default cap for captured output. */
export const DEFAULT_MAX_OUTPUT_CHARS = 20000;
