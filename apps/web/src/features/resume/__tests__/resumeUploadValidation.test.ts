/**
 * @file resumeUploadValidation.test.ts
 * @description Client-side precheck mirrors the backend contract codes.
 */

import { describe, expect, it } from "vitest";

import type { ApiError } from "@/lib/api/base";
import { validateResumeFile } from "../resumeUploadValidation";

function codeOf(fn: () => void): string | null {
  try {
    fn();
  } catch (err) {
    return (err as ApiError).code ?? null;
  }
  return null;
}

describe("validateResumeFile", () => {
  it("accepts a small pdf/docx/md/txt", () => {
    for (const name of ["cv.pdf", "CV.DOCX", "notes.md", "n.txt"]) {
      expect(codeOf(() => validateResumeFile(new File(["x"], name)))).toBeNull();
    }
  });

  it("rejects unsupported extensions as A1002", () => {
    expect(codeOf(() => validateResumeFile(new File(["x"], "cv.exe")))).toBe("A1002");
    expect(codeOf(() => validateResumeFile(new File(["x"], "noext")))).toBe("A1002");
  });

  it("rejects empty files as A0005", () => {
    expect(codeOf(() => validateResumeFile(new File([], "empty.pdf")))).toBe("A0005");
  });

  it("rejects oversize files as A0413", () => {
    const big = new File([new ArrayBuffer(10 * 1024 * 1024 + 1)], "big.pdf");
    expect(codeOf(() => validateResumeFile(big))).toBe("A0413");
  });

  it("rejects overlong filenames as A0003, accepts the 255 boundary", () => {
    expect(codeOf(() => validateResumeFile(new File(["x"], `${"a".repeat(296)}.pdf`)))).toBe("A0003");
    expect(codeOf(() => validateResumeFile(new File(["x"], `${"b".repeat(251)}.txt`)))).toBeNull();
  });
});
