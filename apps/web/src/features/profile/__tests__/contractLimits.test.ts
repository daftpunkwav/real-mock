/**
 * @file contractLimits.test.ts
 * @description Asserts the profileFields catalog stays in sync with openapi UserProfileUpdate.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  PROFILE_FIELD_LIMITS,
  PROFILE_FIELDS,
  REQUIRED_KEYS,
  TECH_DOMAIN_ITEM_MAX,
  TECH_DOMAINS_MAX_COUNT,
} from "../profileFields";
import {
  PROFILE_FIELD_LIMITS as PROFILE_FIELD_LIMITS_REEXPORT,
  TECH_DOMAIN_ITEM_MAX as TECH_DOMAIN_ITEM_MAX_REEXPORT,
  TECH_DOMAINS_MAX_COUNT as TECH_DOMAINS_MAX_COUNT_REEXPORT,
} from "../profileLimits";

const here = dirname(fileURLToPath(import.meta.url));
// __tests__ → profile → features → src → apps/web → apps → repo root
const openapiPath = resolve(here, "../../../../../../openapi.json");
const updateSchema = JSON.parse(readFileSync(openapiPath, "utf-8")).components.schemas
  .UserProfileUpdate;

describe("profileFields vs openapi UserProfileUpdate", () => {
  const props = updateSchema.properties as Record<
    string,
    { maxLength?: number; maxItems?: number; minItems?: number; items?: { maxLength?: number } }
  >;

  it("catalog keys match openapi properties exactly", () => {
    expect(Object.keys(PROFILE_FIELDS).sort()).toEqual(Object.keys(props).sort());
  });

  it("string maxLength matches openapi for every catalog string field", () => {
    for (const [field, limit] of Object.entries(PROFILE_FIELD_LIMITS)) {
      expect(props[field], `openapi ${field}`).toBeDefined();
      expect(props[field]?.maxLength, field).toBe(limit);
    }
    const schemaFields = Object.keys(props).filter((k) => k !== "tech_domains");
    expect(schemaFields).toHaveLength(Object.keys(PROFILE_FIELD_LIMITS).length);
  });

  it("tech_domains item count and item maxLength match openapi", () => {
    const domains = props.tech_domains;
    expect(domains, "openapi tech_domains").toBeDefined();
    expect(domains?.maxItems).toBe(TECH_DOMAINS_MAX_COUNT);
    expect(domains?.minItems).toBe(1);
    expect(domains?.items?.maxLength).toBe(TECH_DOMAIN_ITEM_MAX);
  });

  it("REQUIRED_KEYS match openapi required (order-insensitive)", () => {
    const required = [...(updateSchema.required as string[])].sort();
    expect([...REQUIRED_KEYS].sort()).toEqual(required);
  });

  it("profileLimits re-exports the catalog constants unchanged", () => {
    // The legacy import path must stay a pure pass-through of profileFields.
    expect(PROFILE_FIELD_LIMITS_REEXPORT).toBe(PROFILE_FIELD_LIMITS);
    expect(TECH_DOMAIN_ITEM_MAX_REEXPORT).toBe(TECH_DOMAIN_ITEM_MAX);
    expect(TECH_DOMAINS_MAX_COUNT_REEXPORT).toBe(TECH_DOMAINS_MAX_COUNT);
  });
});
