/**
 * @file profileRules.test.ts
 * @description Unit tests for tech-domain cleanup, completion stats, and content equality.
 */

import { describe, expect, it } from "vitest";

import {
  OPTIONAL_COMPLETION_KEYS,
  completionStatsOf,
  isProfileBlank,
  isProfileContentEqual,
} from "../profileCompletion";
import { REQUIRED_KEYS } from "../profileRequired";
import { cleanTechDomains } from "../techDomains";

import { makeProfile } from "./helpers";

const REQUIRED_FILLED = {
  name: "Ada",
  identity: "employed",
  job_direction: "backend",
  target_role: "engineer",
  self_intro: "Builds APIs",
};

describe("cleanTechDomains", () => {
  it("trims, drops empties, and dedupes while preserving order", () => {
    expect(cleanTechDomains([" Python ", "", "Go", "Python", "  "])).toEqual([
      "Python",
      "Go",
    ]);
  });

  it("returns an empty list for empty input", () => {
    expect(cleanTechDomains([])).toEqual([]);
  });
});

describe("completionStatsOf", () => {
  it("treats a null profile as 0% with every required key missing", () => {
    const stats = completionStatsOf(null);
    expect(stats.filledDomains).toEqual([]);
    expect(stats.requiredMissing).toEqual([...REQUIRED_KEYS]);
    expect(stats.requiredDone).toBe(0);
    expect(stats.optionalDone).toBe(0);
    expect(stats.completionPct).toBe(0);
  });

  it("treats a blank profile as 0% complete", () => {
    const stats = completionStatsOf(makeProfile());
    expect(stats.requiredMissing).toEqual([...REQUIRED_KEYS]);
    expect(stats.completionPct).toBe(0);
  });

  it("counts only required fields when optional ones are empty (6/25)", () => {
    const stats = completionStatsOf(
      makeProfile({ ...REQUIRED_FILLED, tech_domains: ["Python"] }),
    );
    expect(stats.requiredMissing).toEqual([]);
    expect(stats.requiredDone).toBe(REQUIRED_KEYS.length);
    expect(stats.optionalDone).toBe(0);
    expect(stats.completionPct).toBe(Math.round((100 * 6) / 25));
  });

  it("treats whitespace-only tech_domains as missing", () => {
    const stats = completionStatsOf(makeProfile({ ...REQUIRED_FILLED, tech_domains: ["  ", ""] }));
    expect(stats.requiredMissing).toContain("tech_domains");
    expect(stats.filledDomains).toEqual([]);
  });

  it("treats a whitespace-only required string as missing", () => {
    const stats = completionStatsOf(
      makeProfile({ ...REQUIRED_FILLED, tech_domains: ["Python"], name: "   " }),
    );
    expect(stats.requiredMissing).toEqual(["name"]);
    expect(stats.requiredDone).toBe(REQUIRED_KEYS.length - 1);
  });

  it("treats a non-string field value as unfilled", () => {
    // A null sneaking into a Response string field (contract drift) counts as
    // unfilled instead of crashing the stats.
    const stats = completionStatsOf(makeProfile({ city: null as unknown as string }));
    expect(stats.optionalDone).toBe(0);
    expect(stats.completionPct).toBe(0);
  });

  it("normalizes filledDomains with trim and dedupe", () => {
    const stats = completionStatsOf(
      makeProfile({ tech_domains: ["Python", "  ", "Go", "Python"] }),
    );
    expect(stats.filledDomains).toEqual(["Python", "Go"]);
  });

  it("increments optionalDone when one optional completion field is filled", () => {
    const base = makeProfile();
    const statsEmpty = completionStatsOf(base);
    expect(OPTIONAL_COMPLETION_KEYS).toContain("gender");
    const statsOne = completionStatsOf(makeProfile({ ...base, gender: "x" }));
    expect(statsOne.optionalDone).toBe(statsEmpty.optionalDone + 1);
  });

  it("reaches 100% when every required and optional-completion field is filled", () => {
    const allFilled: Record<string, string> = {};
    for (const key of OPTIONAL_COMPLETION_KEYS) {
      allFilled[key] = "v";
    }
    const stats = completionStatsOf(
      makeProfile({ ...REQUIRED_FILLED, tech_domains: ["Python"], ...allFilled }),
    );
    expect(stats.completionPct).toBe(100);
  });
});

describe("isProfileBlank", () => {
  it("treats a catalog-empty profile as blank", () => {
    expect(isProfileBlank(makeProfile())).toBe(true);
  });

  it("is false when a required field is filled", () => {
    expect(isProfileBlank(makeProfile({ name: "Ada" }))).toBe(false);
  });

  it("is false when an inCompletion:false optional is filled", () => {
    expect(isProfileBlank(makeProfile({ portfolio_url: "https://example.com" }))).toBe(false);
  });

  it("treats whitespace-only strings and domains as blank", () => {
    expect(isProfileBlank(makeProfile({ name: "  ", tech_domains: ["", "  "] }))).toBe(true);
  });
});

describe("isProfileContentEqual", () => {
  it("treats two catalog-equal profiles as equal even when id/updated_at differ", () => {
    const a = makeProfile({ name: "Ada", id: 1, updated_at: "2026-01-01T00:00:00Z" });
    const b = makeProfile({ name: "Ada", id: 2, updated_at: "2026-02-02T00:00:00Z" });
    expect(isProfileContentEqual(a, b)).toBe(true);
  });

  it("detects a string field change", () => {
    const a = makeProfile({ name: "Ada" });
    const b = makeProfile({ name: "Bob" });
    expect(isProfileContentEqual(a, b)).toBe(false);
  });

  it("treats trailing spaces and domain order as differences", () => {
    const base = makeProfile({ tech_domains: ["Python", "Go"] });
    expect(isProfileContentEqual(base, makeProfile({ tech_domains: ["Python", "Go "] }))).toBe(
      false,
    );
    expect(isProfileContentEqual(base, makeProfile({ tech_domains: ["Go", "Python"] }))).toBe(false);
  });

  it("detects a tech_domains length change", () => {
    const one = makeProfile({ tech_domains: ["Python"] });
    const two = makeProfile({ tech_domains: ["Python", "Go"] });
    expect(isProfileContentEqual(one, two)).toBe(false);
  });
});
