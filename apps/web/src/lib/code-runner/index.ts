/**
 * @file index.ts
 * @description Public surface of the fenced-code execution module.
 * Rendering code imports only from here.
 */

export {
  DEFAULT_MAX_OUTPUT_CHARS,
  DEFAULT_TIMEOUT_MS,
  type CodeRunner,
  type ExecutionHandle,
  type ExecutionResult,
  type ExecutionStatus,
  type RunLimits,
} from "./types";
export { formatLogArgs, truncateText } from "./output";
export { getRunner, isRunnable, normalizeLanguageId } from "./registry";
