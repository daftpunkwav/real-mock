/**
 * @file contractLimits.test.ts
 * @description Asserts the resumeLimits catalog stays in sync with openapi ResumeDomainLimits.
 *
 * Also checks dimension / tab / mutation-toast i18n keys exist in zh-CN and en.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { DIM_LABEL_KEYS } from "../analysisFormat";
import {
  ANALYSIS_LOCALES,
  DIMENSION_KEYS,
  FILE_TYPE_MAX_LENGTH,
  FILENAME_MAX_LENGTH,
  MAX_PARALLEL_ANALYZE,
  MAX_RESUME_VERSIONS,
  MIN_SCORED_DIMENSIONS,
  PERCENTILE_CEILING,
  PERCENTILE_FLOOR,
  RESUME_MAX_UPLOAD_BYTES,
  RESUME_UPLOAD_EXTENSIONS,
  SCORE_BAND_FAIR,
  SCORE_BAND_STANDOUT,
  SCORE_BAND_STRONG,
  TRUST_KEYS,
} from "../resumeLimits";
import { ANALYSIS_TAB_IDS, TAB_LABEL_KEYS } from "../analysisTabs";
import { resume as zhResume } from "@/i18n/messages/zh-CN/resume";
import { resume as enResume } from "@/i18n/messages/en/resume";

const here = dirname(fileURLToPath(import.meta.url));
const openapiPath = resolve(here, "../../../../../../openapi.json");
const schemas = JSON.parse(readFileSync(openapiPath, "utf-8")).components.schemas as {
  ResumeDomainLimits: {
    properties: Record<string, unknown>;
    "x-resume-catalog"?: {
      allowed_extensions: string[];
      max_upload_bytes: number;
      max_parallel_analyze: number;
      dimension_keys: string[];
      analysis_locales: string[];
      filename_max_length: number;
      file_type_max_length: number;
      max_resume_versions?: number;
      percentile_floor?: number;
      percentile_ceiling?: number;
      min_scored_dimensions?: number;
      score_band_fair?: number;
      score_band_strong?: number;
      score_band_standout?: number;
    };
  };
  SkillTrust: { properties: Record<string, unknown> };
};

describe("resumeLimits vs openapi ResumeDomainLimits", () => {
  const catalog = schemas.ResumeDomainLimits["x-resume-catalog"];

  it("embeds x-resume-catalog on the OpenAPI schema", () => {
    expect(catalog).toBeDefined();
  });

  it("extensions, byte cap, and parallel cap match", () => {
    expect([...RESUME_UPLOAD_EXTENSIONS].sort()).toEqual(
      [...(catalog?.allowed_extensions ?? [])].sort(),
    );
    expect(RESUME_MAX_UPLOAD_BYTES).toBe(catalog?.max_upload_bytes);
    expect(MAX_PARALLEL_ANALYZE).toBe(catalog?.max_parallel_analyze);
  });

  it("dimension keys and locales match exactly", () => {
    expect([...DIMENSION_KEYS]).toEqual(catalog?.dimension_keys);
    expect([...ANALYSIS_LOCALES]).toEqual(catalog?.analysis_locales);
  });

  it("filename / file_type max lengths match", () => {
    expect(FILENAME_MAX_LENGTH).toBe(catalog?.filename_max_length);
    expect(FILE_TYPE_MAX_LENGTH).toBe(catalog?.file_type_max_length);
    expect(MAX_RESUME_VERSIONS).toBe(catalog?.max_resume_versions);
    expect(PERCENTILE_FLOOR).toBe(catalog?.percentile_floor);
    expect(PERCENTILE_CEILING).toBe(catalog?.percentile_ceiling);
    expect(MIN_SCORED_DIMENSIONS).toBe(catalog?.min_scored_dimensions);
  });

  it("score bands match the backend prompt rubric", () => {
    expect(SCORE_BAND_FAIR).toBe(catalog?.score_band_fair);
    expect(SCORE_BAND_STRONG).toBe(catalog?.score_band_strong);
    expect(SCORE_BAND_STANDOUT).toBe(catalog?.score_band_standout);
  });

  it("DIM_LABEL_KEYS covers every catalog dimension key", () => {
    expect(Object.keys(DIM_LABEL_KEYS).sort()).toEqual([...DIMENSION_KEYS].sort());
  });

  it("TRUST_KEYS match openapi SkillTrust properties", () => {
    expect([...TRUST_KEYS].sort()).toEqual(Object.keys(schemas.SkillTrust.properties).sort());
  });

  it("every dimension and tab key exists in zh-CN and en catalogs", () => {
    for (const key of DIMENSION_KEYS) {
      expect(zhResume[`dim.${key}` as keyof typeof zhResume]).toBeTruthy();
      expect(enResume[`dim.${key}` as keyof typeof enResume]).toBeTruthy();
    }
    for (const id of ANALYSIS_TAB_IDS) {
      expect(TAB_LABEL_KEYS[id]).toBe(`analysis.tab.${id}`);
      expect(zhResume[TAB_LABEL_KEYS[id]]).toBeTruthy();
      expect(enResume[TAB_LABEL_KEYS[id]]).toBeTruthy();
    }
  });

  it("mutation toast keys exist in both catalogs", () => {
    const keys = [
      "toast.uploaded",
      "toast.uploadedFallback",
      "toast.uploadFailed",
      "toast.listRefreshFailed",
      "toast.analyzeDone",
      "toast.analyzeFailed",
      "toast.activated",
      "toast.deleted",
      "toast.versionCap",
    ] as const;
    for (const key of keys) {
      expect(zhResume[key].length).toBeGreaterThan(0);
      expect(enResume[key].length).toBeGreaterThan(0);
    }
  });

  it("score band label keys exist in zh-CN and en catalogs", () => {
    const keys = [
      "overview.band.standout",
      "overview.band.solid",
      "overview.band.mixed",
      "overview.band.weak",
      "overview.dimWeight",
    ] as const;
    for (const key of keys) {
      expect(zhResume[key].length).toBeGreaterThan(0);
      expect(enResume[key].length).toBeGreaterThan(0);
    }
  });
});
