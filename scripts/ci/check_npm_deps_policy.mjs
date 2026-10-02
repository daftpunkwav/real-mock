/**
 * Dependency policy check (npm side): fail on any banned package reaching the
 * tree - direct, transitive or override. Scans package-lock.json "packages"
 * keys (the full resolved graph) plus package.json declarations, so an entry
 * in dependency-policy.json blocks every path of arrival.
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const lockPath = join(repoRoot, "apps", "web", "package-lock.json");
const manifestPath = join(repoRoot, "apps", "web", "package.json");
const policyPath = join(repoRoot, "scripts", "ci", "dependency-policy.json");

const policy = JSON.parse(readFileSync(policyPath, "utf8"));
const banned = policy.npm ?? {};

const lock = JSON.parse(readFileSync(lockPath, "utf8"));
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

// Lock entries look like "node_modules/next" or "node_modules/@scope/pkg";
// the package name is everything after the last "node_modules/" segment.
const found = new Set();
for (const key of Object.keys(lock.packages ?? {})) {
  const name = key.split("node_modules/").pop();
  if (name) found.add(name);
}
for (const section of ["dependencies", "devDependencies", "overrides"]) {
  for (const name of Object.keys(manifest[section] ?? {})) found.add(name);
}

const violations = [...found]
  .filter((name) => banned[name] !== undefined)
  .sort();

if (violations.length > 0) {
  console.error("banned npm dependencies present:");
  for (const name of violations) {
    console.error(`  - ${name}: ${banned[name]}`);
  }
  process.exit(1);
}
console.log(`npm dependency policy ok (${found.size} packages scanned)`);
