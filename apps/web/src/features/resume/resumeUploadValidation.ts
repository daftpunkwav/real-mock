/**
 * @file resumeUploadValidation
 * @description Client-side resume file precheck mirroring the backend contract.
 *
 * Responsibilities:
 * - Reject unsupported extensions (A1002), oversize files (A0413), empty files (A0005)
 *   before any bandwidth is spent
 *
 * Throws ApiError with catalog codes so callers localize via formatApiError,
 * exactly as if the backend had rejected the upload.
 *
 * Must not import React, HTTP, or i18n.
 */

import { ApiError } from "@/lib/api/base";
import {
  FILENAME_MAX_LENGTH,
  RESUME_MAX_UPLOAD_BYTES,
  RESUME_UPLOAD_EXTENSIONS,
} from "./resumeLimits";

const BYTES_PER_MB = 1024 * 1024;

function extensionOf(filename: string): string {
  const name = (filename || "").trim().toLowerCase();
  const dot = name.lastIndexOf(".");
  if (dot < 0) return "";
  return name.slice(dot + 1);
}

/** Throw an ApiError when the file cannot be accepted; return void otherwise. */
export function validateResumeFile(file: File): void {
  // Raw filename is persisted verbatim (ORM VARCHAR); reject overlong names
  // here instead of leaking a DB error. Extension length needs no check:
  // the allowlist constrains it to <= 4 chars, mirroring the backend.
  if ((file.name || "").trim().length > FILENAME_MAX_LENGTH) {
    throw new ApiError("File name too long", 0, {
      code: "A0003",
      params: { max: FILENAME_MAX_LENGTH },
    });
  }
  const ext = extensionOf(file.name);
  if (!ext || !(RESUME_UPLOAD_EXTENSIONS as readonly string[]).includes(ext)) {
    throw new ApiError("Unsupported file format", 0, {
      code: "A1002",
      params: { exts: [...RESUME_UPLOAD_EXTENSIONS].sort().join(", ") },
    });
  }
  if (file.size > RESUME_MAX_UPLOAD_BYTES) {
    throw new ApiError("File exceeds the size limit", 0, {
      code: "A0413",
      params: { max: RESUME_MAX_UPLOAD_BYTES / BYTES_PER_MB },
    });
  }
  if (file.size === 0) {
    throw new ApiError("File is empty", 0, { code: "A0005" });
  }
}
