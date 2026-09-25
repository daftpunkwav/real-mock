import { PageSkeleton } from "@/components/loading/PageSkeleton";

export default function Loading() {
  // Real header has no eyebrow/icon; render the body frame only.
  return <PageSkeleton variant="rail-panel" header={false} />;
}
