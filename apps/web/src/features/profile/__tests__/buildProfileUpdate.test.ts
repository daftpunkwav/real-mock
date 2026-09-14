/**
 * @file buildProfileUpdate.test.ts
 * @description Unit tests for building the profile update API payload.
 */

import { describe, expect, it } from "vitest";

import { buildProfileUpdate } from "../buildProfileUpdate";
import { PROFILE_FIELDS } from "../profileFields";
import { makeProfile } from "./helpers";

describe("buildProfileUpdate", () => {
  it("drops id/updated_at and normalizes tech_domains", () => {
    const profile = makeProfile({
      id: 9,
      updated_at: "2026-01-01T00:00:00Z",
      name: "Ada",
      identity: "employed",
      job_direction: "backend",
      target_role: "engineer",
      self_intro: "Builds APIs",
      tech_domains: [" Python ", "", "Go", "Python"],
    });
    const payload = buildProfileUpdate(profile);
    expect(payload).not.toHaveProperty("id");
    expect(payload).not.toHaveProperty("updated_at");
    expect(payload.tech_domains).toEqual(["Python", "Go"]);
    expect(payload.name).toBe("Ada");
  });

  it("emits every catalog key and no extras", () => {
    const payload = buildProfileUpdate(makeProfile());
    expect(Object.keys(payload).sort()).toEqual(Object.keys(PROFILE_FIELDS).sort());
  });

  it("coerces a non-string catalog value to an empty string", () => {
    // If a null ever sneaks into a Response string field (contract drift),
    // the PUT body must carry "" rather than the raw non-string value.
    const profile = makeProfile({ city: null as unknown as string });
    const payload = buildProfileUpdate(profile);
    expect(payload.city).toBe("");
  });
});
