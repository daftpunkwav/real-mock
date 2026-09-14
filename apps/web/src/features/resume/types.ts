/**
 * @file resume feature types
 * @description Shared TypeScript types for resume page components.
 *
 * Responsibilities:
 * - ResumeItem alias used by list/preview/detail
 * - Re-export OpenAPI analysis shapes for UI components
 *
 * Must not import React or HTTP clients.
 */

export type { ResumeItem as Resume } from "./resumeNormalize";
export type { ParsedProfile, ParsedProject } from "./resumeNormalize";

export type {
  ResumeAnalysis,
  DimensionScore,
  InterviewQa,
  RewriteExample,
  SectionReview,
  RepoEvidence,
  RepoVerification,
  ResumePickerItem,
  ResumeResponse,
} from "@/lib/api/contract";

export type { ProjectCard as ProjectCardData } from "@/lib/api/contract";
export type { SkillTrust as SkillTrustData } from "@/lib/api/contract";
export type { CareerAnalysis as CareerAnalysisData } from "@/lib/api/contract";
export type { CompanyFit as CompanyFitData } from "@/lib/api/contract";
export type { TabId } from "./analysisTabs";
