"use client";

/**
 * @file preview/page.tsx
 * @description Original-file preview route shell (Suspense + ResumeFilePreview).
 */

import { Suspense } from "react";
import { ResumeFilePreview } from "@/features/resume";

export default function ResumePreviewPage() {
  return (
    <Suspense fallback={null}>
      <ResumeFilePreview />
    </Suspense>
  );
}
