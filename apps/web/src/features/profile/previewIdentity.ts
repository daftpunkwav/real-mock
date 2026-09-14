/**
 * @file previewIdentity
 * @description Pure helpers for profile preview display (empty vs filled copy).
 *
 * Responsibilities:
 * - Derive avatar initial without inventing placeholder characters
 * - Treat whitespace-only strings as empty
 *
 * Does not import React or i18n.
 */

/** First Unicode code point of a filled name; empty means no invented fallback.

Spreading a string iterates code points (not UTF-16 units, not grapheme
clusters). A ZWJ emoji sequence may still split; names here are not emoji.
*/
export function avatarInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  return [...trimmed][0] ?? "";
}

/** True when a string has non-whitespace content. */
export function isPreviewFilled(value: string): boolean {
  return value.trim().length > 0;
}
