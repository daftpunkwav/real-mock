/** Allow http(s) absolute links and same-origin relative paths / in-page anchors; reject javascript: etc. */
export function safeHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  const t = url.trim();
  try {
    const u = new URL(t, "https://example.invalid");
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    // Same-origin relative paths / and in-page anchors # pass through as-is
    if (t.startsWith("/") || t.startsWith("#")) return t;
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
