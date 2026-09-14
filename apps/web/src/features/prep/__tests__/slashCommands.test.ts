/** slashCommands: parsing, prefix matching, exact resolution. */

import { describe, expect, it } from "vitest";

import { matchSlashCommands, parseCompactArgs, parseSlashCommand, resolveSlashCommand } from "../slashCommands";

describe("parseSlashCommand", () => {
  it("returns null for plain input", () => {
    expect(parseSlashCommand("hello")).toBeNull();
    expect(parseSlashCommand("")).toBeNull();
  });

  it("splits name and args, lowercasing the name", () => {
    expect(parseSlashCommand("/compact")).toEqual({ name: "compact", args: "" });
    expect(parseSlashCommand("/CLEAR now")).toEqual({ name: "clear", args: "now" });
    expect(parseSlashCommand("/")).toEqual({ name: "", args: "" });
  });
});

describe("matchSlashCommands", () => {
  it("matches by prefix with exact first", () => {
    expect(matchSlashCommands("")).toEqual(["clear", "compact", "help"]);
    expect(matchSlashCommands("c")).toEqual(["clear", "compact"]);
    expect(matchSlashCommands("compact")).toEqual(["compact"]);
    expect(matchSlashCommands("zzz")).toEqual([]);
  });
});

describe("resolveSlashCommand", () => {
  it("accepts known names case-insensitively", () => {
    expect(resolveSlashCommand("compact")).toBe("compact");
    expect(resolveSlashCommand("HELP")).toBe("help");
    expect(resolveSlashCommand("unknown")).toBeNull();
    expect(resolveSlashCommand("")).toBeNull();
  });
});

describe("parseCompactArgs", () => {
  it("returns empty params for bare /compact", () => {
    expect(parseCompactArgs("")).toEqual({});
  });

  it("takes a leading intensity keyword plus directive", () => {
    expect(parseCompactArgs("aggressive")).toEqual({ intensity: "aggressive" });
    expect(parseCompactArgs("light keep error stacks")).toEqual({
      intensity: "light",
      directive: "keep error stacks",
    });
    expect(parseCompactArgs("重度 重点保留报错")).toEqual({
      intensity: "aggressive",
      directive: "重点保留报错",
    });
  });

  it("treats unknown first words as directive text", () => {
    expect(parseCompactArgs("please keep decisions")).toEqual({ directive: "please keep decisions" });
  });
});
