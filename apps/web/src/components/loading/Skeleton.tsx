"use client";

/**
 * @file Skeleton.tsx
 * @description Shimmer placeholder primitives shared by route and query loading
 * frames (the visual comes from the `.skeleton` class in globals.css).
 */

/** One shimmer block; size it with className utilities. Decorative only. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/** Multi-line text placeholder; the last line is shortened like a paragraph. */
export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-2.5 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}
