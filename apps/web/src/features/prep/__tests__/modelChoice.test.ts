/** resolveSelectedModel: id matching, null-default, unknown-id. */

import { describe, expect, it } from "vitest";

import { resolveSelectedModel } from "../modelChoice";
import type { ModelProfile } from "@/types";

const profile = (id: number): ModelProfile => ({ id }) as ModelProfile;

describe("resolveSelectedModel", () => {
  const models = [profile(1), profile(2)];

  it("returns the matching model id", () => {
    expect(resolveSelectedModel(models, 2, profile(9))?.id).toBe(2);
  });

  it("returns the default profile for null id", () => {
    expect(resolveSelectedModel(models, null, profile(9))?.id).toBe(9);
  });

  it("returns null when the default is missing", () => {
    expect(resolveSelectedModel(models, null, null)).toBeNull();
  });

  it("returns null for an unknown id", () => {
    expect(resolveSelectedModel(models, 42, profile(9))).toBeNull();
  });
});
