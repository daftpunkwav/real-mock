/**
 * Unified HTTP domain-client entry (named by product capability, not backend package).
 *
 * - ``settingsHttp``: providers / models / bindings
 * - ``profileHttp``: user profile
 * - ``resumeHttp``: resumes
 * - ``prepCoachHttp``: interview prep coach
 * - ``prepMemoryHttp``: prep long-term memories
 * - ``interviewHttp``: mock interview sessions
 * - ``recordsHttp``: history / ledger / report retry
 * - ``reportHttp``: single-session report
 * - ``growthHttp``: growth tracking
 */

export { settingsHttp } from "./settingsHttp";
export { profileHttp } from "./profileHttp";
export { resumeHttp } from "./resumeHttp";
export { prepCoachHttp, type PrepStreamCallbacks } from "./prepCoachHttp";
export { prepMemoryHttp } from "./prepMemoryHttp";
export { interviewHttp } from "./interviewHttp";
export { recordsHttp } from "./recordsHttp";
export { reportHttp } from "./reportHttp";
export { growthHttp, type SystemGrowthInsights } from "./growthHttp";

/** OpenAPI contract types */
export * from "./contract";
