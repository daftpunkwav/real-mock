/**
 * @file resume feature barrel
 * @description Public exports for the resume feature consumed by app routes.
 *
 * Responsibilities:
 * - Re-export page-facing hooks, section components, and shared types
 *
 * Limits live in resumeLimits.ts; this barrel keeps the public surface narrow.
 * Internal hooks (collection/mutations) stay unexported.
 * Confirm dialogs live in `@/components/ConfirmDialog` — list items import them there.
 */

export { useResumeList } from "./useResumeList";
export type { Resume, ResumeAnalysis } from "./types";
export { ResumePageHead } from "./components/ResumePageHead";
export { ResumeUploadArea } from "./components/ResumeUploadArea";
export { ResumeList } from "./components/ResumeList";
export { ResumeDetailPanel } from "./components/ResumeDetailPanel";
export { ResumePreviewCard } from "./components/ResumePreviewCard";
export { ResumeOverviewCard } from "./components/ResumeOverviewCard";
export { ResumeTipsCard } from "./components/ResumeTipsCard";
export { ResumeFilePreview } from "./components/ResumeFilePreview";
export { AnalysisPanel } from "./components/AnalysisPanel";
