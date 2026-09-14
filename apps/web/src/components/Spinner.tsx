"use client";

/** Generic spinner: inherits text color by default; size/color overridable by caller. */
export function Spinner({
  className = "h-4 w-4",
  color = "current",
}: {
  className?: string;
  color?: "current" | "primary";
}) {
  const border = color === "primary" ? "border-[var(--primary)]" : "border-current";
  return (
    <span className={`block anim-spin rounded-full border-2 ${border} border-t-transparent ${className}`} />
  );
}
