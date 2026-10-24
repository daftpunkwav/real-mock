/**
 * Tests for scripts/ci/check_npm_deps_policy.mjs (`node --test scripts/ci/test/`).
 *
 * The gate was only exercised by the pipeline it guards; these tests pin the
 * parsing rules (resolved-version graph, alias resolution, version collation,
 * duplicate-instance rule) against synthetic lock/manifest/policy trees.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { compareVersions, scan, splitVersion } from "../check_npm_deps_policy.mjs";

test("splitVersion drops build metadata and splits the prerelease", () => {
  assert.deepEqual(splitVersion("1.2.3"), ["1.2.3", ""]);
  assert.deepEqual(splitVersion("1.2.3-rc.1"), ["1.2.3", "rc.1"]);
  assert.deepEqual(splitVersion("1.2.3+sha.abc"), ["1.2.3", ""]);
  assert.deepEqual(splitVersion("1.2.3-rc.1+sha.abc"), ["1.2.3", "rc.1"]);
});

test("compareVersions collates numerically, not alphabetically", () => {
  assert.ok(compareVersions("8.10.0", "8.2.1") > 0, "8.10.0 must be newer than 8.2.1");
  assert.ok(compareVersions("8.2.1", "8.10.0") < 0);
  assert.equal(compareVersions("1.0.0", "1.0.0"), 0);
});

test("compareVersions ranks a prerelease older than its release", () => {
  assert.ok(compareVersions("1.0.0-rc.1", "1.0.0") < 0);
  assert.ok(compareVersions("1.0.0", "1.0.0-rc.1") > 0);
  assert.equal(compareVersions("1.0.0-rc.1", "1.0.0-rc.1"), 0);
});

const POLICY = { npm: { bannedpkg: "banned by policy" } };

test("scan flags a banned package by any path of arrival", () => {
  const result = scan({
    lock: {
      packages: {
        "node_modules/next": { version: "16.0.0" },
        "apps/web/node_modules/bannedpkg": { version: "1.0.0" },
      },
    },
    manifest: { dependencies: { next: "^16" } },
    policy: POLICY,
  });
  assert.deepEqual(result.violations, ["bannedpkg"]);
  assert.deepEqual(result.aliasViolations, []);
  assert.deepEqual(result.duplicatedRuntimeDeps, []);
});

test("scan sees a ban through an alias install", () => {
  const result = scan({
    lock: { packages: { "node_modules/local-name": { version: "npm:bannedpkg@1.0.0" } } },
    manifest: { dependencies: { "local-name": "npm:bannedpkg@^1" } },
    policy: POLICY,
  });
  assert.deepEqual(result.violations, []);
  // The alias is inspected once in the lock and once in the manifest, so the
  // ban surfaces through both declarations.
  assert.equal(result.aliasViolations.length, 2);
  for (const alias of result.aliasViolations) {
    assert.equal(alias.installed, "local-name");
    assert.equal(alias.real, "bannedpkg");
  }
});

test("scan counts only non-dev copies as runtime instances", () => {
  const result = scan({
    lock: {
      packages: {
        "node_modules/left-pad": { version: "1.3.0", dev: true },
        "apps/web/node_modules/left-pad": { version: "2.0.0" },
      },
    },
    manifest: { dependencies: { "left-pad": "^2" } },
    policy: POLICY,
  });
  // The dev-only copy ships nowhere, so a single runtime instance remains.
  assert.deepEqual(result.duplicatedRuntimeDeps, []);
});

test("scan reports a duplicated runtime dependency newest-first", () => {
  const result = scan({
    lock: {
      packages: {
        "node_modules/three": { version: "0.160.0" },
        "apps/web/node_modules/three": { version: "0.180.0" },
      },
    },
    manifest: { dependencies: { three: "^0.180.0" } },
    policy: POLICY,
  });
  assert.equal(result.duplicatedRuntimeDeps.length, 1);
  assert.equal(result.duplicatedRuntimeDeps[0].name, "three");
  assert.deepEqual(result.duplicatedRuntimeDeps[0].versions, ["0.160.0", "0.180.0"]);
});

test("scan reports a clean tree as clean", () => {
  const result = scan({
    lock: { packages: { "node_modules/next": { version: "16.0.0" } } },
    manifest: { dependencies: { next: "^16" } },
    policy: POLICY,
  });
  assert.equal(result.scanned, 1);
  assert.deepEqual(result.violations, []);
  assert.deepEqual(result.aliasViolations, []);
  assert.deepEqual(result.duplicatedRuntimeDeps, []);
});
