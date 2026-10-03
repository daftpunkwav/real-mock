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
// Alias installs ("local": "npm:real@...") hide the real package behind a
// local folder name - the spec string is the only place the real name shows,
// so both the lock entry version and the manifest spec are inspected.
const found = new Set();
const aliases = []; // { installed, target: "npm:<realname>@..." }
for (const [key, entry] of Object.entries(lock.packages ?? {})) {
  const installed = key.split("node_modules/").pop();
  if (installed) found.add(installed);
  if (typeof entry?.version === "string" && entry.version.startsWith("npm:")) {
    aliases.push({ installed, target: entry.version });
  }
}
for (const section of ["dependencies", "devDependencies", "overrides"]) {
  for (const [installed, spec] of Object.entries(manifest[section] ?? {})) {
    found.add(installed);
    if (typeof spec === "string" && spec.startsWith("npm:")) {
      aliases.push({ installed, target: spec });
    }
  }
}

const violations = [...found]
  .filter((name) => banned[name] !== undefined)
  .sort();

const aliasViolations = aliases
  .map((alias) => ({ ...alias, real: alias.target.match(/^npm:([^@]+)/)?.[1] ?? "" }))
  .filter((alias) => banned[alias.real] !== undefined)
  .sort((a, b) => a.installed.localeCompare(b.installed));

if (violations.length > 0 || aliasViolations.length > 0) {
  console.error("banned npm dependencies present:");
  for (const name of violations) {
    console.error(`  - ${name}: ${banned[name]}`);
  }
  for (const alias of aliasViolations) {
    console.error(
      `  - ${alias.installed} (alias for ${alias.real}): ${banned[alias.real]}`,
    );
  }
  process.exit(1);
}
console.log(`npm dependency policy ok (${found.size} packages scanned)`);
