/**
 * i18n usage audit: catches two failure modes the parity test cannot see.
 *
 * 1. Ghost keys - a string passed to a translator that no catalog defines
 *    (a typo renders literally at runtime).
 * 2. Dead keys - catalog entries no source path can reach; they drift in
 *    both locales and rot silently.
 *
 * Translators are bound to a namespace at creation and called under any
 * local name (t, meta, ...), so "referenced" is decided verbatim: a catalog
 * key counts as referenced when it appears as a complete quoted string
 * anywhere outside the message data itself. Template literals mark their
 * static prefix as dynamic - every key under `phase.` is considered used
 * when `phase.${id}` appears. Everything genuinely unreachable needs the
 * allowlist.
 *
 * Known boundary (deliberate): call sites are not bound to their namespace -
 * doing that requires translator-binding analysis across every file. Two
 * consequences, both underreporting-only (the gate never false-blocks):
 * a bare key defined in several namespaces is considered live if any one of
 * them references it, and ghost candidates are limited to the translator
 * call shapes recognized below.
 *
 * Scanned: apps/web/src minus tests and minus i18n/messages (the data being
 * audited); the i18n module itself (LocaleProvider, error catalog) counts as
 * a consumer.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const srcRoot = join(webRoot, "src");
const messagesRoot = join(srcRoot, "i18n", "messages", "en");
const allowlistPath = join(scriptDir, "i18n-usage-allowlist.json");

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (full === join(srcRoot, "i18n", "messages")) continue;
      yield* walk(full);
    } else {
      yield full;
    }
  }
}

// --- catalog keys -----------------------------------------------------------

const known = new Set(); // bare keys ("action.confirm")
const knownQualified = new Set(); // "common.action.confirm"
for (const file of readdirSync(messagesRoot)) {
  if (!file.endsWith(".ts")) continue;
  const ns = file.replace(/\.ts$/, "");
  const text = readFileSync(join(messagesRoot, file), "utf8");
  for (const match of text.matchAll(/^\s*"([a-z0-9.-]+)":/gm)) {
    known.add(match[1]);
    knownQualified.add(`${ns}.${match[1]}`);
  }
}
if (known.size === 0) {
  console.error("no catalog keys found - parse failure?");
  process.exit(1);
}

// --- source corpus (referenced-key evidence) --------------------------------

let corpus = "";
const callSites = [];
for (const file of walk(srcRoot)) {
  if (!/\.(ts|tsx)$/.test(file)) continue;
  if (file.includes("__tests__") || /\.test\.(ts|tsx)$/.test(file)) continue;
  const text = readFileSync(file, "utf8");
  corpus += text + "\n";
  // Ghost candidates keep call-site context: translator-shaped invocations.
  for (const match of text.matchAll(/(?:\bt\b|\bmeta\b|\.has\b)\(\s*["'`]([a-z0-9.-]+)["'`]/g)) {
    callSites.push(match[1]);
  }
  for (const match of text.matchAll(
    /peekMessage\(\s*[^,]+,\s*["'`]([a-z0-9-]+)["'`]\s*,\s*["'`]([a-z0-9.-]+)["'`]/g,
  )) {
    // Bare key only: the qualified "ns.key" form is not in `known` and would
    // be misreported as a ghost.
    callSites.push(match[2]);
  }
}

// Template literals with a dotted static prefix - `dim.${d.key}` even when
// not written directly inside t(...) - mark every catalog key under that
// prefix as referenced, but only when the family actually exists in the
// catalog: an unrelated `debug.${id}` with no debug.* keys suppresses
// nothing.
const dynamicPrefixes = new Set();
for (const match of corpus.matchAll(/`([^`\n]*?)\$\{/g)) {
  const prefix = match[1].match(/([a-z0-9-]+(?:\.[a-z0-9-]+)*)\.$/);
  if (prefix) dynamicPrefixes.add(`${prefix[1]}.`);
}
for (const prefix of [...dynamicPrefixes]) {
  const familyExists = [...known].some((key) => key.startsWith(prefix));
  if (!familyExists) dynamicPrefixes.delete(prefix);
}

function referencedVerbatim(key) {
  return (
    corpus.includes(`"${key}"`) || corpus.includes(`'${key}'`) || corpus.includes(`\`${key}\``)
  );
}

// --- allowlist --------------------------------------------------------------

let allowlist = [];
try {
  allowlist = JSON.parse(readFileSync(allowlistPath, "utf8"));
} catch {
  allowlist = [];
}

// --- verdicts ---------------------------------------------------------------

const ghostCandidates = new Set(callSites);
const ghosts = [...ghostCandidates].filter((key) => key.includes(".") && !known.has(key)).sort();

const dead = [...known]
  .filter((key) => {
    if (referencedVerbatim(key)) return false;
    if (allowlist.includes(key)) return false;
    if (allowlist.includes([...knownQualified].find((q) => q.endsWith(`.${key}`)) ?? "")) {
      return false;
    }
    for (const prefix of dynamicPrefixes) {
      if (key.startsWith(prefix)) return false;
    }
    return true;
  })
  .sort();

if (ghosts.length > 0) {
  console.error("ghost keys (referenced, undefined in catalog):");
  for (const key of ghosts) console.error(`  - ${key}`);
}
if (dead.length > 0) {
  console.error(`dead keys (defined, never referenced verbatim; ${allowlist.length} allowlisted):`);
  for (const key of dead) console.error(`  - ${key}`);
}
if (ghosts.length === 0 && dead.length === 0) {
  console.log(`i18n usage ok (${known.size} keys audited)`);
  process.exit(0);
}
process.exit(1);
