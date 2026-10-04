// @vitest-environment jsdom
/**
 * @file fields.test.tsx
 * @description Accessible-name contract for the custom role/company text inputs:
 * each visible <label> must be programmatically associated with its input so
 * screen readers announce the field (getByLabelText resolves only through
 * htmlFor/id or nesting).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { InterviewConfig, Options } from "@/lib/api/contract";

import { SetupFields } from "../fields";

vi.mock("@/i18n", () => {
  // Keys-as-text translator with the `has` probe optionLabels relies on;
  // `has` returns false so catalog labels fall back to their raw ids.
  const t = Object.assign((key: string) => key, { has: () => false });
  return {
    useT: () => t,
    useLocale: () => ({ locale: "zh-CN" }),
  };
});

vi.mock("../controls", () => ({
  Select: () => <div data-testid="select-stub" />,
  CompanyGrid: () => <div data-testid="company-grid-stub" />,
  ResumeWarning: () => <div data-testid="resume-warning-stub" />,
}));

vi.mock("../processorCard", () => ({
  ProcessorCard: () => <div data-testid="processor-card-stub" />,
}));

function makeOptions(): Options {
  return {
    roles: ["backend_engineer"],
    levels: ["mid_engineer"],
    experience_years: ["0-1"],
    companies: [
      {
        id: "bytedance",
        name: "ByteDance",
        style: "pragmatic",
        focus_areas: [],
        sample_questions: [],
        interview_flow: "",
        pressure_level: "",
      },
    ],
    personalities: [{ id: "professional", name: "Professional", description: "" }],
    interview_styles: [{ id: "deep_dive", name: "Deep dive", description: "" }],
    workflow_types: [{ id: "technical", name: "Technical", phases: [] }],
    avatars: [{ id: "professional_male", name: "Male", voice: "" }],
    scenes: [{ id: "meeting_room", name: "Meeting room" }],
    silence_nudge_seconds: 10,
  };
}

function makeConfig(): InterviewConfig {
  return {
    // Values outside the catalog ids route both fields to their custom input.
    role: "数据库内核工程师",
    level: "mid_engineer",
    company: "自定义公司",
    workflow_type: "technical",
    personality: "professional",
    strictness: 5,
    interview_style: "deep_dive",
    resume_id: null,
    avatar_id: "professional_male",
    scene_id: "meeting_room",
    reference_detail: "outline",
  };
}

function renderFields(onConfig: (patch: Partial<InterviewConfig>) => void = () => {}) {
  return render(
    <SetupFields
      options={makeOptions()}
      config={makeConfig()}
      resumes={[]}
      creating={false}
      multiRound={false}
      onMultiRound={() => {}}
      chatModels={[]}
      sttModels={[]}
      ttsModels={[]}
      chatModelId={null}
      sttModelId={null}
      ttsModelId={null}
      effort="medium"
      referenceDetail="outline"
      defaultBindings={null}
      onConfig={onConfig}
      setChatModelId={() => {}}
      setSttModelId={() => {}}
      setTtsModelId={() => {}}
      setEffort={() => {}}
      setReferenceDetail={() => {}}
    />,
  );
}

describe("SetupFields custom input labels", () => {
  afterEach(cleanup);

  it("associates the custom role and company labels with their inputs", () => {
    renderFields();
    expect(screen.getByLabelText("setup.role.custom")).toBeTruthy();
    expect(screen.getByLabelText("setup.company.custom")).toBeTruthy();
  });

  it("routes typed text into onConfig for both custom fields", () => {
    const onConfig = vi.fn();
    renderFields(onConfig);

    fireEvent.change(screen.getByLabelText("setup.role.custom"), {
      target: { value: "内核工程师" },
    });
    expect(onConfig).toHaveBeenCalledWith({ role: "内核工程师" });

    fireEvent.change(screen.getByLabelText("setup.company.custom"), {
      target: { value: "ACME" },
    });
    expect(onConfig).toHaveBeenCalledWith({ company: "ACME" });
  });
});
