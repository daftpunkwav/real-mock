/**
 * @file profileFields
 * @description Single frontend catalog for UserProfileUpdate fields.
 *
 * Responsibilities:
 * - Declare each update-contract field once (kind, limits, required, completion)
 * - Derive limits, required keys, optional-completion keys, and PUT mapping keys
 *
 * Aligned with openapi UserProfileUpdate via contractLimits.test.ts.
 * Does not import React, HTTP, or i18n. Labels live in profileRequired.ts.
 */

import type { UserProfileUpdate } from "@/lib/api/contract";

type RequiredStringField = {
  kind: "string";
  maxLength: number;
  required: true;
};

type OptionalStringField = {
  kind: "string";
  maxLength: number;
  required: false;
  /** When true, the field counts toward the optional completion KPI. */
  inCompletion: boolean;
};

type RequiredListField = {
  kind: "list";
  itemMaxLength: number;
  itemMaxCount: number;
  required: true;
};

type ProfileFieldSpec = RequiredStringField | OptionalStringField | RequiredListField;

/**
 * One row per UserProfileUpdate key. Adding an API field without a row here
 * fails the `satisfies` check (and contractLimits.test.ts after openapi regen).
 */
export const PROFILE_FIELDS = {
  name: { kind: "string", maxLength: 100, required: true },
  gender: { kind: "string", maxLength: 20, required: false, inCompletion: true },
  identity: { kind: "string", maxLength: 50, required: true },
  school: { kind: "string", maxLength: 200, required: false, inCompletion: true },
  major: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  graduation_year: { kind: "string", maxLength: 20, required: false, inCompletion: true },
  job_direction: { kind: "string", maxLength: 100, required: true },
  experience_years: { kind: "string", maxLength: 50, required: false, inCompletion: true },
  work_years_detail: { kind: "string", maxLength: 100, required: false, inCompletion: false },
  current_company: { kind: "string", maxLength: 200, required: false, inCompletion: true },
  expected_salary: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  self_intro: { kind: "string", maxLength: 2000, required: true },
  tech_domains: { kind: "list", itemMaxLength: 50, itemMaxCount: 20, required: true },
  target_role: { kind: "string", maxLength: 100, required: true },
  github_username: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  portfolio_url: { kind: "string", maxLength: 500, required: false, inCompletion: false },
  linkedin_url: { kind: "string", maxLength: 500, required: false, inCompletion: false },
  city: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  preferred_languages: { kind: "string", maxLength: 200, required: false, inCompletion: false },
  career_highlights: { kind: "string", maxLength: 2000, required: false, inCompletion: true },
  open_to_remote: { kind: "string", maxLength: 20, required: false, inCompletion: false },
  notice_period: { kind: "string", maxLength: 50, required: false, inCompletion: false },
  education_level: { kind: "string", maxLength: 50, required: false, inCompletion: true },
  expected_city: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  email: { kind: "string", maxLength: 200, required: false, inCompletion: true },
  phone: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  certificates: { kind: "string", maxLength: 2000, required: false, inCompletion: true },
  english_level: { kind: "string", maxLength: 100, required: false, inCompletion: true },
  signature_projects: { kind: "string", maxLength: 2000, required: false, inCompletion: true },
  strengths: { kind: "string", maxLength: 2000, required: false, inCompletion: true },
  weaknesses: { kind: "string", maxLength: 2000, required: false, inCompletion: true },
} as const satisfies Record<keyof UserProfileUpdate, ProfileFieldSpec>;

/** Reject extra catalog keys that UserProfileUpdate does not declare. */
type _CatalogKeysExact = [
  Exclude<keyof typeof PROFILE_FIELDS, keyof UserProfileUpdate>,
] extends [never]
  ? true
  : never;
const _catalogKeysExact: _CatalogKeysExact = true;
void _catalogKeysExact;

export type ProfileFieldKey = keyof typeof PROFILE_FIELDS;

export type RequiredKey = {
  [K in ProfileFieldKey]: (typeof PROFILE_FIELDS)[K]["required"] extends true ? K : never;
}[ProfileFieldKey];

export type StringFieldKey = {
  [K in ProfileFieldKey]: (typeof PROFILE_FIELDS)[K]["kind"] extends "string" ? K : never;
}[ProfileFieldKey];

export type OptionalCompletionKey = {
  [K in ProfileFieldKey]: (typeof PROFILE_FIELDS)[K] extends {
    required: false;
    inCompletion: true;
  }
    ? K
    : never;
}[ProfileFieldKey];

const FIELD_KEYS = Object.keys(PROFILE_FIELDS) as ProfileFieldKey[];

/** Insertion order matches PROFILE_FIELDS (same as UserProfileUpdate). */
export const PROFILE_UPDATE_KEYS = FIELD_KEYS as readonly (keyof UserProfileUpdate)[];

export const REQUIRED_KEYS = FIELD_KEYS.filter(
  (key): key is RequiredKey => PROFILE_FIELDS[key].required,
);

export const OPTIONAL_COMPLETION_KEYS = FIELD_KEYS.filter(
  (key): key is OptionalCompletionKey => {
    const spec = PROFILE_FIELDS[key];
    return !spec.required && spec.kind === "string" && spec.inCompletion;
  },
);

export const PROFILE_FIELD_LIMITS = Object.fromEntries(
  FIELD_KEYS.filter((key): key is StringFieldKey => PROFILE_FIELDS[key].kind === "string").map(
    (key) => [key, PROFILE_FIELDS[key].maxLength],
  ),
) as { readonly [K in StringFieldKey]: number };

export const TECH_DOMAIN_ITEM_MAX = PROFILE_FIELDS.tech_domains.itemMaxLength;
export const TECH_DOMAINS_MAX_COUNT = PROFILE_FIELDS.tech_domains.itemMaxCount;
