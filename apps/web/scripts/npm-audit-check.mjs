#!/usr/bin/env node
/**
 * Gate `npm audit` on high/critical with an explicit allowlist.
 *
 * npm audit has no per-advisory ignore flag (unlike pip-audit --ignore-vuln),
 * so this checker filters `npm audit --json` output against
 * npm-audit-allowlist.json. Any high/critical finding not on the list fails
 * the gate (exit 1). Allowlisted-but-absent entries are reported so the list
 * stays pruned, but do not fail.
 *
 * Fail-closed invariants: empty/unparseable input, a report without a
 * vulnerabilities section, or metadata claiming high/critical findings we
 * did not enumerate, never passes.
 *
 * Usage: `npm run audit` (CI frontend job runs the same command). The audit
 * JSON arrives via stdin so no nested npm process (and its environment) is
 * involved.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const allowlistPath = join(root, "npm-audit-allowlist.json");

function fail(message) {
  console.error(`npm-audit-check: FAIL: ${message}`);
  process.exit(1);
}

let allowlist;
try {
  allowlist = JSON.parse(readFileSync(allowlistPath, "utf8"));
} catch (err) {
  fail(`cannot read allowlist ${allowlistPath}: ${err.message}`);
}
const allowedIds = new Set((allowlist.allow ?? []).map((e) => e.id));

let raw;
try {
  raw = readFileSync(0, "utf8");
} catch (err) {
  fail(`cannot read audit JSON from stdin: ${err.message}`);
}
let report;
try {
  report = JSON.parse(raw || "{}");
} catch {
  fail("stdin is not parseable audit JSON (pipe `npm audit --json` into this checker)");
}
if (report == null || typeof report !== "object" || report.vulnerabilities == null) {
  fail("audit report has no vulnerabilities section");
}

const vulns = report.vulnerabilities ?? {};
const metaCounts =
  report.metadata && typeof report.metadata === "object"
    ? (report.metadata.vulnerabilities ?? {})
    : null;
const seenIds = new Set();
const blocking = [];
let countedHigh = 0;
for (const [name, v] of Object.entries(vulns)) {
  const severity = v?.severity ?? "";
  if (severity !== "high" && severity !== "critical") continue;
  countedHigh += 1;
  const vias = Array.isArray(v.via) ? v.via : [];
  const ghsaIds = vias
    .filter((x) => typeof x !== "string")
    .map((x) => x.url?.split("/").pop() ?? "")
    .filter(Boolean);
  for (const id of ghsaIds) seenIds.add(id);
  // Fail closed: findings without an attributable advisory id always block.
  const unlisted = ghsaIds.filter((id) => !allowedIds.has(id));
  if (unlisted.length > 0 || ghsaIds.length === 0) {
    blocking.push({ name, severity, range: v.range, advisory: unlisted });
  }
}

if (metaCounts != null) {
  const metaHigh = (metaCounts.high ?? 0) + (metaCounts.critical ?? 0);
  if (metaHigh !== countedHigh) {
    fail(
      `audit metadata reports ${metaHigh} high/critical but ${countedHigh} were enumerated`,
    );
  }
}

for (const entry of allowlist.allow ?? []) {
  if (!seenIds.has(entry.id)) {
    console.log(`npm-audit-check: allowlist entry not observed (prune?): ${entry.id}`);
  }
}

if (blocking.length > 0) {
  for (const b of blocking) {
    console.error(
      `npm-audit-check: blocking ${b.severity} in ${b.name} ${b.range ?? ""} advisories=${(b.advisory ?? []).join(",") || "n/a"}`,
    );
  }
  console.error(
    "npm-audit-check: resolve the findings or document them in npm-audit-allowlist.json",
  );
  process.exit(1);
}

console.log("npm-audit-check: OK (no unlisted high/critical findings)");
