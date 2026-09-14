/**
 * @file resumeSelection
 * @description Pure preview-id picker for the resume list.
 *
 * Responsibilities:
 * - Keep the current preview when it still exists
 * - Otherwise prefer the active resume, then the first row
 *
 * Must not import React or HTTP.
 */

export function pickPreviewId(
  list: ReadonlyArray<{ id: number; is_active?: boolean }>,
  prev: number | null,
): number | null {
  if (prev != null && list.some((row) => row.id === prev)) return prev;
  const active = list.find((row) => row.is_active);
  return active?.id ?? list[0]?.id ?? null;
}
