/** Growth-domain types.
 *
 * Backend `/v1/growth/*` responses have no OpenAPI schema (see root openapi.json,
 * empty response content); this hand-written definition is the frontend contract SSOT
 * until the backend adds response_model and we switch to `@/lib/api/contract`.
 */

export interface GrowthRecord {
  id: number;
  session_id: number;
  weak_skills: string[];
  training_plan: string[];
  created_at: string;
}
