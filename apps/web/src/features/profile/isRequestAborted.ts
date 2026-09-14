/**
 * @file isRequestAborted
 * @description Detect cancelled HTTP calls from the shared API client.
 *
 * Responsibilities:
 * - Recognize abort/cancel errors so hooks can stay silent
 *
 * Depends only on ApiError from the API base layer.
 */

import { ApiError } from "@/lib/api/base";

/** True when the request was aborted (unload, retry, or discard-and-leave). */
export function isRequestAborted(error: unknown): boolean {
  // NET0002 = request aborted (see ApiError codes in the API client).
  return error instanceof ApiError && error.code === "NET0002";
}
