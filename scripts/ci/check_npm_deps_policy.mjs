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
 *
 * The parsing/comparison logic is exported and pinned by
 * scripts/ci/test/check_npm_deps_policy.test.mjs (`node --test`); the file
 * still runs as the gate when executed directly.
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const lockPath = join(repoRoot, "apps", "web", "package-lock.json");
const manifestPath = join(repoRoot, "apps", "web", "package.json");
const policyPath = join(repoRoot, "scripts", "ci", "dependency-policy.json");

/**
 * Split a version into its numeric core and its prerelease part.
 *
 * Build metadata ("+sha") does not take part in the precedence, so it is
 * dropped before the split.
 */
export function splitVersion(version) {
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
export function compareVersions(a, b) {
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

/**
 * The package an alias install points at, or null when the spec is not one.
 *
 * Alias installs ("local": "npm:real@...") hide the real package behind a
 * local folder name, so the spec string is the only place the real name shows.
 */
function aliasTarget(spec) {
  if (typeof spec !== "string" || !spec.startsWith("npm:")) return null;
  return spec.match(/^npm:(.+)@[^@]+$/)?.[1] ?? spec.slice(4);
}

/**
 * The package name a lock entry declares, when it differs from the folder the
 * entry is installed under, or null when the two agree.
 *
 * npm records an alias install under the local folder name and writes the real
 * package into the entry's "name" field, with the plain version beside it
 * ("node_modules/alias": { "name": "real", "version": "1.0.0" }). The folder
 * name then hides the real package, so the entry is inspected as well.
 */
function entryAlias(entry, installed) {
  if (!installed) return null;
  const declared = typeof entry?.name === "string" ? entry.name : null;
  if (!declared || declared === installed) return null;
  return declared;
}

/**
 * What one lock entry contributes: the installed package name, the package an
 * alias points at, and the version the entry resolves to.
 *
 * Lock entries look like "node_modules/next" or "node_modules/@scope/pkg";
 * the package name is everything after the last "node_modules/" segment.
 */
function lockEntryFacts(key, entry) {
  const installed = key.split("node_modules/").pop();
  const version = typeof entry?.version === "string" ? entry.version : null;
  return {
    installed,
    version,
    // The entry's own name covers the alias installs npm writes with a plain
    // version; the spec form covers the lock's "npm:real@..." version.
    real: entryAlias(entry, installed) ?? aliasTarget(version),
    // Only copies that reach the shipped bundle count as instances of a
    // runtime dependency. npm marks a copy that exists solely for the dev
    // toolchain with "dev"; "npm ci --omit=dev" does not install it, so it is
    // not a second instance of the library. "devOptional" copies are part of
    // the production tree (they are reachable through an optional production
    // edge), so they still count.
    runtime: Boolean(installed) && version !== null && !entry.dev,
  };
}

/**
 * The resolved versions of the runtime copies, grouped by package name.
 */
function groupRuntimeVersions(facts) {
  const versionsByName = new Map();
  for (const fact of facts) {
    const versions = versionsByName.get(fact.installed) ?? new Set();
    versions.add(fact.version);
    versionsByName.set(fact.installed, versions);
  }
  return versionsByName;
}

/**
 * The packages, aliases and runtime versions the lock file resolves.
 */
function scanLock(lock) {
  const facts = Object.entries(lock.packages ?? {}).map(([key, entry]) => lockEntryFacts(key, entry));
  return {
    found: new Set(facts.filter((fact) => fact.installed).map((fact) => fact.installed)),
    aliases: facts
      .filter((fact) => fact.real)
      .map((fact) => ({ installed: fact.installed, real: fact.real })),
    versionsByName: groupRuntimeVersions(facts.filter((fact) => fact.runtime)),
  };
}

/**
 * Every dependency declaration of the manifest.
 *
 * The three sections are read with static property access: a computed lookup
 * on a plain object is a generic object injection sink.
 */
function manifestEntries(manifest) {
  return [
    ...Object.entries(manifest.dependencies ?? {}),
    ...Object.entries(manifest.devDependencies ?? {}),
    ...Object.entries(manifest.overrides ?? {}),
  ];
}

/**
 * The packages and aliases the manifest declares.
 */
function scanManifest(manifest) {
  const entries = manifestEntries(manifest);
  const aliases = entries
    .map(([installed, spec]) => ({ installed, real: aliasTarget(spec) }))
    .filter((alias) => alias.real);
  return { found: new Set(entries.map(([installed]) => installed)), aliases };
}

/**
 * Run both policy rules over one lock/manifest/policy triple.
 *
 * Pure: the caller owns reading the files and reporting the result, so the
 * tests can pin the rules against synthetic trees. The banned packages are
 * indexed in a Map, so a package name read from the lock file is a lookup and
 * never a computed property access on a plain object.
 *
 * Returns the scanned package count, the banned packages that reached the tree
 * (each with the policy reason), the banned packages that reached it through
 * an alias install, and the direct runtime dependencies that resolved to more
 * than one version.
 */
export function scan({ lock, manifest, policy }) {
  const banned = new Map(Object.entries(policy.npm ?? {}));
  const lockScan = scanLock(lock);
  const manifestScan = scanManifest(manifest);
  const found = new Set([...lockScan.found, ...manifestScan.found]);
  const aliases = [...lockScan.aliases, ...manifestScan.aliases];

  const violations = [...found]
    .filter((name) => banned.has(name))
    // Package names, so the alphabetical order is the intended one; the
    // comparator is spelled out so no sort in this file relies on the default
    // order of the runtime.
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ name, reason: banned.get(name) }));

  const aliasViolations = aliases
    .filter((alias) => banned.has(alias.real))
    .sort((a, b) => a.installed.localeCompare(b.installed))
    .map((alias) => ({ installed: alias.installed, real: alias.real, reason: banned.get(alias.real) }));

  // A direct runtime dependency that resolves to several versions in the shipped
  // tree ships several instances. Only runtime dependencies are checked, and only
  // the copies that reach the bundle count: a duplicate that exists solely for
  // the dev toolchain stays out of the shipped bundle and is a normal npm
  // resolution outcome.
  const duplicatedRuntimeDeps = Object.keys(manifest.dependencies ?? {})
    .map((name) => ({ name, versions: [...(lockScan.versionsByName.get(name) ?? [])].sort(compareVersions) }))
    .filter((dep) => dep.versions.length > 1)
    .sort((a, b) => a.name.localeCompare(b.name));

  return { scanned: found.size, violations, aliasViolations, duplicatedRuntimeDeps };
}

/**
 * Report the banned packages that reached the tree.
 */
function reportBannedDependencies(violations, aliasViolations) {
  console.error("banned npm dependencies present:");
  for (const violation of violations) {
    console.error(`  - ${violation.name}: ${violation.reason}`);
  }
  for (const alias of aliasViolations) {
    console.error(`  - ${alias.installed} (alias for ${alias.real}): ${alias.reason}`);
  }
}

/**
 * Report the direct runtime dependencies that ship more than one instance.
 */
function reportDuplicatedRuntimeDependencies(duplicatedRuntimeDeps) {
  console.error("direct runtime dependencies resolved to more than one version:");
  for (const dep of duplicatedRuntimeDeps) {
    console.error(`  - ${dep.name}: ${dep.versions.join(", ")}`);
  }
  console.error(
    "keep the range compatible with the package that actually uses it, or drop the unused direct dependency",
  );
}

function main() {
  const policy = JSON.parse(readFileSync(policyPath, "utf8"));
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const { scanned, violations, aliasViolations, duplicatedRuntimeDeps } = scan({ lock, manifest, policy });

  if (violations.length > 0 || aliasViolations.length > 0) {
    reportBannedDependencies(violations, aliasViolations);
    process.exit(1);
  }

  if (duplicatedRuntimeDeps.length > 0) {
    reportDuplicatedRuntimeDependencies(duplicatedRuntimeDeps);
    process.exit(1);
  }

  console.log(`npm dependency policy ok (${scanned} packages scanned)`);
}

// Run as the gate only when executed directly (`node check_npm_deps_policy.mjs`
// from security.yml); importing the module must stay side-effect free so the
// tests can pin the exported logic.
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main();
}
