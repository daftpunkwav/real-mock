/**
 * @file helpers.ts
 * @description Resume test fixtures. Fill parsed_profile so new fields stay defined.
 *
 * Nested objects in `overrides` replace the default field; they are not deep-merged.
 */

import type { ResumeAnalysis, ResumeResponse } from "@/lib/api/contract";
import { normalizeResume, type ResumeItem } from "../resumeNormalize";

export function makeResumeResponse(overrides: Partial<ResumeResponse> = {}): ResumeResponse {
  const id = overrides.id ?? 1;
  return {
    id,
    filename: "cv.pdf",
    file_type: "pdf",
    parsed_profile: {
      name: "Ada",
      education: [],
      work_experience: [],
      skills: ["Python"],
      projects: [{ name: "RealMock" }],
      summary: "Backend engineer",
      target_role: "",
      email: "",
      phone: "",
      city: "",
      layout_notes: "",
      parse_degraded: false,
    },
    is_active: false,
    score: null,
    analysis: {},
    created_at: "2026-01-01T00:00:00Z",
    family_id: id,
    version_n: 1,
    parse_status: "done",
    parse_error: "",
    ...overrides,
  };
}

export function makeResume(overrides: Partial<ResumeResponse> = {}): ResumeItem {
  return normalizeResume(makeResumeResponse(overrides));
}

/**
 * Typed review payload with every analysis tab populated.
 * Nested objects in `overrides` replace the default field; they are not deep-merged.
 */
export function makeAnalysis(overrides: Partial<ResumeAnalysis> = {}): ResumeAnalysis {
  return {
    score: 70,
    role_fit_summary: "Fits backend roles",
    seniority_estimate: "Mid",
    overall_narrative: "Overall narrative body",
    layout_review: "cramped columns",
    typography_review: "weak hierarchy",
    content_review: "needs metrics",
    headline: "Backend engineer",
    first_impression: "Strong opener",
    salary_positioning: "market median",
    project_cards: [
      {
        name: "Voyager",
        score: 80,
        one_line: "Agent runtime",
        highlights: ["MCP"],
        risks: ["solo"],
        deep_questions: [
          {
            question: "How is the registry generated?",
            intent: "Probe understanding of the metadata pipeline",
            answer_points: ["Field declarations drive generation"],
          },
        ],
      },
    ],
    skill_trust: { solid: ["Python"], claimed: [], missing: ["K8s"] },
    ...overrides,
  };
}
