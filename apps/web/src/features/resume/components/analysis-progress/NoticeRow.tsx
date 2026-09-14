"use client";

/**
 * @file NoticeRow
 * @description Warning notice row for the live review log (e.g. vision degradation).
 */

import { TriangleAlert } from "lucide-react";
import type { ReviewNoticeItem } from "../../reviewProgress";

export function NoticeRow({ item }: { item: ReviewNoticeItem }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-[12px] leading-relaxed text-amber-200"
    >
      <TriangleAlert size={13} className="mt-0.5 shrink-0" aria-hidden />
      <p className="min-w-0">{item.content}</p>
    </div>
  );
}
