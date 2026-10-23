/**
 * @file prepDeepLink
 * @description Deep-link contract between the resume deep-review sheet and the
 * prep coach chat.
 *
 * The link carries the owning resume id plus the seeded question text; the
 * prep page consumes (and strips) the params once its resources have loaded,
 * pairing the target session with the same resume the analysis belongs to.
 *
 * Lives in lib so both features share one contract: the resume feature builds
 * the link, the prep feature parses it, and neither reaches into the other's
 * internals.
 */

/** Search-param keys consumed by the prep page. */
export const PREP_DEEP_LINK_PARAMS = ["resume", "q"] as const;

/**
 * Build a /prep deep link seeding one question bound to one resume.
 * `resumeId` may be null (analysis persisted before resume pairing existed);
 * the prep page then falls back to its currently selected resume.
 */
export const buildPrepDeepLink = (resumeId: number | null, question: string): string => {
  const params = new URLSearchParams();
  if (resumeId != null) params.set("resume", String(resumeId));
  params.set("q", question);
  return `/prep?${params.toString()}`;
};

/** Parsed prep deep-link payload (empty when the URL carries none). */
export interface PrepDeepLink {
  resumeId: number | null;
  question: string;
}

/** Parse the deep-link params from a query string; null when no question is present. */
export const parsePrepDeepLink = (search: string): PrepDeepLink | null => {
  const params = new URLSearchParams(search);
  const question = params.get("q")?.trim();
  if (!question) return null;
  const rawResume = params.get("resume");
  const resumeId = rawResume !== null && /^\d+$/.test(rawResume) ? Number(rawResume) : null;
  return { resumeId, question };
};
