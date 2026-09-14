/**
 * @file resume domain types
 * @description OpenAPI re-exports plus UI aliases for resume analysis cards.
 *
 * Analysis shapes use the generated contract as SSOT. The list/preview `Resume`
 * alias is ResumeResponse; the resume feature normalizes parsed_profile arrays
 * into ResumeItem before rendering.
 */

export type {
  ResumeAnalysis,
  DimensionScore,
  RewriteExample,
  SectionReview,
  RepoEvidence,
  RepoVerification,
  ResumePickerItem,
  ResumeResponse,
  CandidateProfile,
} from "@/lib/api/contract";

/** UI components keep the *Data suffix; underlying types are OpenAPI schemas. */
export type { ProjectCard as ProjectCardData } from "@/lib/api/contract";
export type { SkillTrust as SkillTrustData } from "@/lib/api/contract";
export type { CareerAnalysis as CareerAnalysisData } from "@/lib/api/contract";
export type { CompanyFit as CompanyFitData } from "@/lib/api/contract";

/** activate endpoint returns a full ResumeResponse. */
export type ResumeActivateResponse = import("@/lib/api/contract").ResumeResponse;

/** Wire type for HTTP payloads; feature UI uses ResumeItem after normalize. */
export type Resume = import("@/lib/api/contract").ResumeResponse;
