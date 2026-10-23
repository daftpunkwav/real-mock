/**
 * Dependency policy check (npm side): fail on any banned package reaching the
 * tree - direct, transitive or override. Scans package-lock.json "packages"
 * keys (the full resolved graph) plus package.json declarations, so an entry
 * in dependency-policy.json blocks every path of arrival.
 *
 * Second rule: a direct runtime dependency must resolve to a single version in
 * the shipped tree. Two instances of one runtime library (a hoisted copy plus a
 * nested copy) ship twice, double the patch surface, and break libraries that
 * keep per-module state (the classic "two three.js instances" failure). A
 * direct dependency nobody imports is the usual cause: the version range then
 * fails to satisfy the package that really uses it, so npm nests a second copy.
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
const versionsByName = new Map(); // installed name -> Set of resolved versions
for (const [key, entry] of Object.entries(lock.packages ?? {})) {
  const installed = key.split("node_modules/").pop();
  if (installed) found.add(installed);
  if (typeof entry?.version === "string" && entry.version.startsWith("npm:")) {
    aliases.push({ installed, target: entry.version });
  }
  if (installed && typeof entry?.version === "string" && !entry.dev) {
    // Only copies that reach the shipped bundle count as instances of a
    // runtime dependency. npm marks a copy that exists solely for the dev
    // toolchain with "dev"; "npm ci --omit=dev" does not install it, so it is
    // not a second instance of the library. "devOptional" copies are part of
    // the production tree (they are reachable through an optional production
    // edge), so they still count.
    if (!versionsByName.has(installed)) versionsByName.set(installed, new Set());
    versionsByName.get(installed).add(entry.version);
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

/**
 * Split a version into its numeric core and its prerelease part.
 *
 * Build metadata ("+sha") does not take part in the precedence, so it is
 * dropped before the split.
 */
function splitVersion(version) {
  const withoutBuild = version.split("+")[0];
  const dash = withoutBuild.indexOf("-");
  if (dash === -1) return [withoutBuild, ""];
  return [withoutBuild.slice(0, dash), withoutBuild.slice(dash + 1)];
}

/**
 * Compare two npm versions by semver precedence.
 *
 * Version strings do not sort alphabetically: "8.10.0" is newer than
 * "8.2.1", but an alphabetical order puts it first. A numeric collation
 * compares the digit runs as numbers, so the reported versions are listed in
 * the order they were resolved. A prerelease ("1.0.0-rc.1") is older than
 * the release it precedes ("1.0.0") - a plain numeric collation ranks it the
 * other way round, so the two parts are compared separately.
 */
function compareVersions(a, b) {
  const [aCore, aPre] = splitVersion(a);
  const [bCore, bPre] = splitVersion(b);
  if (aCore !== bCore) {
    return aCore.localeCompare(bCore, undefined, { numeric: true, sensitivity: "base" });
  }
  if (aPre === bPre) return 0;
  if (!aPre) return 1;
  if (!bPre) return -1;
  return aPre.localeCompare(bPre, undefined, { numeric: true, sensitivity: "base" });
}

const violations = [...found]
  .filter((name) => banned[name] !== undefined)
  // Package names, so the alphabetical order is the intended one; the
  // comparator is spelled out so no sort in this file relies on the default
  // order of the runtime.
  .sort((a, b) => a.localeCompare(b));

const aliasViolations = aliases
  .map((alias) => ({ ...alias, real: alias.target.match(/^npm:(.+)@[^@]+$/)?.[1] ?? alias.target.slice(4) }))
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

// A direct runtime dependency that resolves to several versions in the shipped
// tree ships several instances. Only runtime dependencies are checked, and only
// the copies that reach the bundle count: a duplicate that exists solely for
// the dev toolchain stays out of the shipped bundle and is a normal npm
// resolution outcome.
const duplicatedRuntimeDeps = Object.keys(manifest.dependencies ?? {})
  .map((name) => ({ name, versions: [...(versionsByName.get(name) ?? [])].sort(compareVersions) }))
  .filter((dep) => dep.versions.length > 1)
  .sort((a, b) => a.name.localeCompare(b.name));

if (duplicatedRuntimeDeps.length > 0) {
  console.error("direct runtime dependencies resolved to more than one version:");
  for (const dep of duplicatedRuntimeDeps) {
    console.error(`  - ${dep.name}: ${dep.versions.join(", ")}`);
  }
  console.error(
    "keep the range compatible with the package that actually uses it, or drop the unused direct dependency",
  );
  process.exit(1);
}

console.log(`npm dependency policy ok (${found.size} packages scanned)`);
