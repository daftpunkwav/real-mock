/**
 * OpenAPI schema re-exports shared by REST/SSE/WS paths. Hand-written event types live in @/types/domains.
 */

import type { components, paths } from "@/types/generated/api";

export type ApiPaths = paths;
export type ApiSchemas = components["schemas"];

/* Profile / resume / settings domain */
export type UserProfileResponse = components["schemas"]["UserProfileResponse"];
export type UserProfileUpdate = components["schemas"]["UserProfileUpdate"];
export type ResumeResponse = components["schemas"]["ResumeResponse"];
export type ResumeDomainLimits = components["schemas"]["ResumeDomainLimits"];
export type CandidateProfile = components["schemas"]["CandidateProfile"];
export type ResumeAnalysis = components["schemas"]["ResumeAnalysis"];
export type DimensionScore = components["schemas"]["DimensionScore"];
export type InterviewQa = components["schemas"]["InterviewQa"];
export type RewriteExample = components["schemas"]["RewriteExample"];
export type SectionReview = components["schemas"]["SectionReview"];
export type ProjectCard = components["schemas"]["ProjectCard"];
export type SkillTrust = components["schemas"]["SkillTrust"];
export type CareerAnalysis = components["schemas"]["CareerAnalysis"];
export type CompanyFit = components["schemas"]["CompanyFit"];
export type RepoEvidence = components["schemas"]["RepoEvidence"];
export type RepoVerification = components["schemas"]["RepoVerification"];
export type LLMTestResponse = components["schemas"]["LLMTestResponse"];
export type CompanyInfo = components["schemas"]["CompanyInfo"];

/* prep domain */
export type PrepSessionSummary = components["schemas"]["PrepSessionSummary"];
export type PrepSessionCreateResponse = components["schemas"]["PrepSessionCreateResponse"];
export type PrepMessageResponse = components["schemas"]["PrepMessageResponse"];
export type PrepHistoryMessage = components["schemas"]["PrepHistoryMessage"];
export type PrepToolStep = components["schemas"]["PrepToolStep"];
export type PrepSearchHit = components["schemas"]["PrepSearchHit"];
export type PrepSearchGroup = components["schemas"]["PrepSearchGroup"];
export type PrepMemorySummary = components["schemas"]["PrepMemorySummary"];
export type PrepMemoryDetail = components["schemas"]["PrepMemoryDetail"];

/* interview domain */
export type InterviewSession = components["schemas"]["InterviewSessionResponse"];
export type Options = components["schemas"]["OptionsResponse"];
export type ResumePickerItem = components["schemas"]["ResumePickerItem"];
export type InterviewConfig = components["schemas"]["InterviewConfig"];
export type ChatMessage = components["schemas"]["ChatMessage"];
export type InterviewReport = components["schemas"]["DebriefReport"];
export type ScoreBreakdown = components["schemas"]["ScoreBreakdown"];
export type GetReportResponse = components["schemas"]["ReportResponse"];
export type FinishInterviewResponse = components["schemas"]["FinishInterviewResponse"];
export type InterviewProcessResponse = components["schemas"]["InterviewProcessResponse"];
export type ProcessCreateRequest = components["schemas"]["ProcessCreateRequest"];
export type ProcessCreatedResponse = components["schemas"]["ProcessCreatedResponse"];
export type ProcessRoundItem = components["schemas"]["ProcessRoundItem"];
export type PlanStepView = components["schemas"]["PlanStepView"];
