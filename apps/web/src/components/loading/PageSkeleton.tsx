"use client";

/**
 * @file PageSkeleton.tsx
 * @description Layout-shaped loading frames: the page shell paints instantly and
 * blocks shimmer until data lands. One component serves both phases — route-level
 * loading.tsx (navigation swap) and the in-page query fallback — so the skeleton
 * hands off to real content without a layout flash.
 *
 * Variants mirror real page structures; keep them in sync when a page layout
 * changes structurally. `header={false}` for pages whose real header renders
 * above their query fallback.
 */

import { Skeleton, SkeletonText } from "./Skeleton";

function HeaderBlock() {
  // Mirrors the real page-header geometry (icon badge + eyebrow + title row,
  // default page-header margins) so the swap from skeleton to real header
  // does not shift content below.
  return (
    <div className="page-header">
      <div className="flex items-start gap-3">
        <Skeleton className="h-9 w-9 shrink-0 rounded-[var(--radius-md)]" />
        <div className="min-w-0">
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="mt-1.5 h-[31px] w-44" />
        </div>
      </div>
    </div>
  );
}

function SkeletonCard({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return <div className={`surface-card p-4 ${className}`}>{children}</div>;
}

function RowsCard({ rows = 4 }: { rows?: number }) {
  return (
    <SkeletonCard className="space-y-3.5">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-2.5 w-1/5" />
          </div>
          <Skeleton className="h-5 w-12 rounded-full" />
        </div>
      ))}
    </SkeletonCard>
  );
}

function AsideCard({ lines = 4 }: { lines?: number }) {
  return (
    <SkeletonCard className="space-y-3">
      <Skeleton className="h-3.5 w-24" />
      <SkeletonText lines={lines} />
    </SkeletonCard>
  );
}

/** Wide list column + 300px sticky aside (resume, history). */
function SplitBody() {
  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-4">
        <RowsCard rows={5} />
        <SkeletonCard>
          <SkeletonText lines={3} />
        </SkeletonCard>
      </div>
      <div className="space-y-3">
        <AsideCard lines={5} />
        <AsideCard lines={3} />
      </div>
    </div>
  );
}

/** Toolbar + card grid (prep, interview setup). */
function BoardBody() {
  return (
    <div className="space-y-3">
      <SkeletonCard className="!p-3">
        <div className="flex gap-2">
          <Skeleton className="h-8 w-40 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
          <div className="flex-1" />
          <Skeleton className="h-8 w-24 rounded-md" />
        </div>
      </SkeletonCard>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <SkeletonCard key={i} className="h-28" />
        ))}
      </div>
    </div>
  );
}

/** Sectioned form grid (profile). */
function FormBody() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {Array.from({ length: 4 }, (_, i) => (
        <SkeletonCard key={i} className="space-y-3">
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-9 w-full rounded-md" />
          <Skeleton className="h-9 w-full rounded-md" />
        </SkeletonCard>
      ))}
    </div>
  );
}

/** Stat cards + split below (growth). */
function StatsBody() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <SkeletonCard key={i} className="h-20" />
        ))}
      </div>
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <SkeletonCard className="h-40" />
          <SkeletonCard className="h-32" />
        </div>
        <div className="space-y-3">
          <AsideCard lines={4} />
        </div>
      </div>
    </div>
  );
}

/** Category rail + detail panel (settings). */
function RailPanelBody() {
  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[200px_1fr]">
      <SkeletonCard className="!p-2 space-y-1">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full rounded-md" />
        ))}
      </SkeletonCard>
      <SkeletonCard className="min-h-64 space-y-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-full rounded-md" />
        <Skeleton className="h-9 w-full rounded-md" />
        <SkeletonText lines={2} />
      </SkeletonCard>
    </div>
  );
}

const BODIES = {
  split: <SplitBody />,
  board: <BoardBody />,
  form: <FormBody />,
  stats: <StatsBody />,
  "rail-panel": <RailPanelBody />,
} as const;

export type PageSkeletonVariant = keyof typeof BODIES;

export function PageSkeleton({
  variant,
  header = true,
  shell = true,
}: {
  variant: PageSkeletonVariant;
  /** Render the skeleton page header; false when the real header renders above. */
  header?: boolean;
  /** Wrap in the page-shell container; false inside a page that already owns one. */
  shell?: boolean;
}) {
  const body = (
    <>
      {header ? <HeaderBlock /> : null}
      {BODIES[variant]}
    </>
  );
  return shell ? (
    <div className="page-shell anim-rise" role="status" aria-busy="true">
      {body}
    </div>
  ) : (
    <div role="status" aria-busy="true">
      {body}
    </div>
  );
}
