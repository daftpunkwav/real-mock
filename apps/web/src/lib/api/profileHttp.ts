/**
 * @file profileHttp
 * @description REST client for the user profile resource (`/v1/profile`).
 *
 * Responsibilities:
 * - GET / PUT / POST-clear profile payloads against the OpenAPI contract types
 * - Reject empty 200 bodies so callers never treat `undefined` as profile state
 * - Forward AbortSignal for load/save cancellation
 *
 * Must not own form validation, completion stats, or UI state.
 */

import type { UserProfileResponse, UserProfileUpdate } from "@/lib/api/contract";
import { ApiError, request } from "@/lib/api/base";

function expectBody<T>(data: T, message: string): T {
  if (data === undefined || data === null) {
    throw new ApiError(message, 0, { code: "NET0003" });
  }
  return data;
}

export const profileHttp = {
  getProfile: async (options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<UserProfileResponse>("/v1/profile", { signal: options?.signal }),
      "Failed to load profile: server returned an empty response",
    ),
  updateProfile: async (data: UserProfileUpdate, options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<UserProfileResponse>("/v1/profile", {
        method: "PUT",
        body: JSON.stringify(data),
        signal: options?.signal,
      }),
      "Failed to save profile: server returned an empty response",
    ),
  clearProfile: async (options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<UserProfileResponse>("/v1/profile/clear", {
        method: "POST",
        signal: options?.signal,
      }),
      "Failed to clear profile: server returned an empty response",
    ),
};
