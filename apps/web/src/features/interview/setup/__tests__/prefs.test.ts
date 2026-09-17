// @vitest-environment jsdom
/** Setup preference persistence: round trips, malformed payloads, and catalog validation. */

import { beforeEach, describe, expect, it } from "vitest";

import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";

import {
  SETUP_PREFS_KEY,
  readSetupPrefs,
  restoreModelId,
  restoreSetupConfig,
  writeSetupPrefs,
} from "../prefs";

function makeOptions(overrides: Partial<Options> = {}): Options {
  return {
    roles: ["backend_engineer", "frontend_engineer"],
    levels: ["junior_engineer", "mid_engineer", "intern"],
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
      {
        id: "alibaba",
        name: "Alibaba",
        style: "systematic",
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
    ...overrides,
  };
}

const resumes: ResumePickerItem[] = [
  { id: 7, filename: "a.pdf", is_active: true },
  { id: 9, filename: "b.pdf", is_active: false },
];

describe("readSetupPrefs / writeSetupPrefs", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns empty prefs when storage is empty", () => {
    expect(readSetupPrefs()).toEqual({});
  });

  it("returns empty prefs for malformed payloads", () => {
    localStorage.setItem(SETUP_PREFS_KEY, "{not json");
    expect(readSetupPrefs()).toEqual({});
    localStorage.setItem(SETUP_PREFS_KEY, JSON.stringify(["array"]));
    expect(readSetupPrefs()).toEqual({});
  });

  it("drops fields with wrong types and keeps valid ones", () => {
    localStorage.setItem(
      SETUP_PREFS_KEY,
      JSON.stringify({
        config: { role: "backend_engineer", strictness: 9 },
        multiRound: true,
        chatModelId: 3,
        sttModelId: "three",
        ttsModelId: null,
        effort: "high",
        referenceDetail: "bogus",
      }),
    );
    expect(readSetupPrefs()).toEqual({
      config: { role: "backend_engineer", strictness: 9 },
      multiRound: true,
      chatModelId: 3,
      ttsModelId: null,
      effort: "high",
    });
  });

  it("round-trips the full preference set", () => {
    const prefs = {
      config: { role: "intern_custom", level: "intern", strictness: 1 },
      multiRound: true,
      chatModelId: 1,
      sttModelId: 2,
      ttsModelId: 3,
      effort: "max" as const,
      referenceDetail: "full" as const,
    };
    writeSetupPrefs(prefs);
    expect(readSetupPrefs()).toEqual(prefs);
  });
});

describe("restoreSetupConfig", () => {
  it("returns an empty patch for missing stored config", () => {
    expect(restoreSetupConfig(undefined, makeOptions(), resumes)).toEqual({});
  });

  it("keeps valid preset ids and in-range strictness", () => {
    const patch = restoreSetupConfig(
      {
        role: "frontend_engineer",
        level: "intern",
        company: "alibaba",
        workflow_type: "technical",
        interview_style: "deep_dive",
        personality: "professional",
        strictness: 7,
        avatar_id: "professional_male",
        scene_id: "meeting_room",
        resume_id: 9,
      },
      makeOptions(),
      resumes,
    );
    expect(patch).toEqual({
      role: "frontend_engineer",
      level: "intern",
      company: "alibaba",
      workflow_type: "technical",
      interview_style: "deep_dive",
      personality: "professional",
      strictness: 7,
      avatar_id: "professional_male",
      scene_id: "meeting_room",
      resume_id: 9,
    });
  });

  it("keeps non-blank custom role/company text but drops blank ones", () => {
    const patch = restoreSetupConfig(
      { role: "  音视频工程师  ", company: "某小厂" },
      makeOptions(),
      resumes,
    );
    expect(patch.role).toBe("  音视频工程师  ");
    expect(patch.company).toBe("某小厂");
    expect(restoreSetupConfig({ role: "   " }, makeOptions(), resumes).role).toBeUndefined();
  });

  it("drops stale enum/avatar/scene/resume ids and out-of-range strictness", () => {
    // Stored payloads are untrusted: simulate ids that no catalog lists anymore.
    const stale = {
      role: "deleted_role",
      level: "principal",
      company: "gone_corp",
      workflow_type: "phone_screen",
      interview_style: "rapid_fire",
      personality: "robot",
      strictness: 42,
      avatar_id: "hologram",
      scene_id: "mars",
      resume_id: 999,
    } as unknown as Partial<InterviewConfig>;
    const patch = restoreSetupConfig(stale, makeOptions(), resumes);
    // Stale role/company ids degrade to custom free-form text (indistinguishable
    // from user-typed names); everything else falls back to the defaults.
    expect(patch).toEqual({ role: "deleted_role", company: "gone_corp" });
  });

  it("drops a resume id that no longer exists", () => {
    expect(
      restoreSetupConfig({ resume_id: 7 }, makeOptions(), resumes).resume_id,
    ).toBe(7);
    expect(
      restoreSetupConfig({ resume_id: 7 }, makeOptions(), []).resume_id,
    ).toBeUndefined();
  });
});

describe("restoreModelId", () => {
  const models = [{ id: 1 }, { id: 2 }];

  it("keeps a stored id still present in the bucket", () => {
    expect(restoreModelId(2, models)).toBe(2);
  });

  it("falls back to null for missing or stale ids", () => {
    expect(restoreModelId(undefined, models)).toBeNull();
    expect(restoreModelId(null, models)).toBeNull();
    expect(restoreModelId(Number.NaN, models)).toBeNull();
    expect(restoreModelId(3, models)).toBeNull();
  });
});
