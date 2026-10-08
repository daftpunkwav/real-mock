// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ResumePage from "@/app/resume/page";
import { ResumePreviewCard } from "../components/ResumePreviewCard";
import { PREVIEW_SKILL_MAX } from "../resumeLimits";
import { keyedPreviewProjects } from "../resumePreview";
import type { Resume } from "../types";

const state = vi.hoisted(() => ({ previewResume: null as Resume | null }));
vi.mock("@/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("@/features/resume", async () => ({
  ResumePreviewCard: (await import("../components/ResumePreviewCard")).ResumePreviewCard,
  useResumeList: () => ({ ...state, resumes: [], analyzingIds: [], analyzeProgressById: {} }),
  ResumePageHead: () => null,
  ResumeUploadArea: () => null,
  ResumeList: () => null,
  ResumeDetailPanel: () => null,
  ResumeOverviewCard: () => null,
  ResumeTipsCard: () => null,
}));
afterEach(cleanup);

const resume = (id: number): Resume => {
  return {
    id,
    filename: `cv-${id}.pdf`,
    file_type: "pdf",
    score: null,
    created_at: "2026-10-06T00:00:00Z",
    parse_status: "done",
    parse_error: "",
    is_active: false,
    family_id: id,
    version_n: 1,
    parsed_profile: {
      name: "",
      education: [],
      work_experience: [],
      parse_degraded: false,
      summary: "",
      projects: [],
      skills: Array.from({ length: PREVIEW_SKILL_MAX + 1 }, (_, i) => `skill${i}`),
    },
  };
};

it("caps skills when selecting another resume, including returning to the first", () => {
  state.previewResume = resume(1);
  const { rerender } = render(<ResumePage />);
  fireEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(screen.queryByText(`skill${PREVIEW_SKILL_MAX}`)).not.toBeNull();
  state.previewResume = resume(2);
  rerender(<ResumePage />);
  expect(screen.queryByText(`skill${PREVIEW_SKILL_MAX}`)).toBeNull();
  state.previewResume = resume(1);
  rerender(<ResumePage />);
  expect(screen.queryByText(`skill${PREVIEW_SKILL_MAX}`)).toBeNull();
});

it("preserves project row identity across reordering of same-named projects", () => {
  const first = { name: "App", description: "First" };
  const second = { name: "App", description: "Second" };
  const row = resume(1);
  row.parsed_profile.projects = [first, second];
  const { rerender } = render(<ResumePreviewCard resume={row} />);
  const before = screen.getAllByRole("listitem");
  rerender(
    <ResumePreviewCard
      resume={{ ...row, parsed_profile: { ...row.parsed_profile, projects: [second, first] } }}
    />,
  );
  const after = screen.getAllByRole("listitem");
  expect(after[0]).toBe(before[1]);
  expect(after[1]).toBe(before[0]);
});

it("keeps duplicate project keys unique and independent of unrelated insertions", () => {
  const project = { name: "App", description: "Same", url: "https://example.com" };
  const before = keyedPreviewProjects([project, { ...project }]);
  const after = keyedPreviewProjects([{ name: "Other" }, { ...project }, project]);
  expect(new Set(before.map(({ key }) => key)).size).toBe(2);
  expect(after.slice(1).map(({ key }) => key)).toEqual(before.map(({ key }) => key));
});
