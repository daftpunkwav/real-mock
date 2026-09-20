/** Allow http(s) absolute links and same-origin relative paths / in-page anchors; reject javascript: etc. */
export function safeHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  const t = url.trim();
  try {
    // The base only exists to parse schemes; resolving a bare relative path
    // against it would render a dead link to that placeholder host.
    const u = new URL(t, "https://example.invalid");
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    if (t.startsWith("/") || t.startsWith("#")) return t;
    // Only an explicit scheme makes this absolute ("//host" already matched the
    // branch above). A bare relative path has no same-origin base here, and
    // resolving it against the parse base would render a dead link.
    if (!/^[a-z][a-z\d+\-.]*:/i.test(t)) return null;
    return u.href;
  } catch {
    return null;
  }
}

/** Absolute http(s) URLs only (reject relative paths and dangerous schemes). */
export function safeAbsoluteHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  const t = url.trim();
  try {
    const u = new URL(t);
    if (u.protocol === "http:" || u.protocol === "https:") return u.toString();
  } catch {
    /* invalid */
  }
  return null;
}
