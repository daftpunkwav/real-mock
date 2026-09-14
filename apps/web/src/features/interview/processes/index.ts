"use client";

/** Continue-process feature (multi-round interview entry point). */

export { ContinueProcesses } from "./ContinueProcesses";
export { useProcessContinuation } from "./useProcessContinuation";
export {
  buildNextRoundIndex,
  selectEligibleProcesses,
  type EligibleProcess,
} from "./eligibility";
