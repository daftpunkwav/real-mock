/**
 * @file techDomains
 * @description Pure helpers for tech_domains list normalization.
 *
 * Responsibilities:
 * - Trim, drop empties, dedupe while preserving order
 *
 * Aligned with backend `clean_tech_domains` for string[] input (trim, drop
 * empties, order-preserving dedupe). The Python helper also skips non-strings
 * and parses JSON; this function assumes TypeScript `string[]`.
 */

export function cleanTechDomains(domains: string[]): string[] {
  return [...new Set(domains.map((d) => d.trim()).filter(Boolean))];
}
