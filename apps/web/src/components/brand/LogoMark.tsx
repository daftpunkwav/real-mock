"use client";

import { useId } from "react";

/**
 * RealMock brand mark: a speech bubble carrying a voice waveform —
 * the two halves of a mock interview (dialogue + speech), filled with
 * the brand blue ramp so it sits right in both themes.
 */
export function LogoMark({ size = 26, className }: { size?: number; className?: string }) {
  const gradientId = useId();
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
      className={className}
      style={{ flexShrink: 0, display: "block" }}
    >
      <defs>
        <linearGradient
          id={gradientId}
          x1="4"
          y1="4"
          x2="28"
          y2="28"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#7aabff" />
          <stop offset="0.55" stopColor="#4285f4" />
          <stop offset="1" stopColor="#1a63d8" />
        </linearGradient>
      </defs>
      <path
        d="M16 3.5C9.1 3.5 3.5 8.4 3.5 14.4c0 3.4 1.8 6.4 4.7 8.4-.2 1.7-.9 3.3-2.1 4.6-.3.3-.1.9.4.8 2.6-.4 4.9-1.5 6.6-3 1 .2 1.9.3 2.9.3 6.9 0 12.5-5 12.5-11S22.9 3.5 16 3.5Z"
        fill={`url(#${gradientId})`}
      />
      <rect x="9.4" y="11.8" width="2.5" height="6.2" rx="1.25" fill="#fff" opacity="0.92" />
      <rect x="14.75" y="8.8" width="2.5" height="12.2" rx="1.25" fill="#fff" />
      <rect x="20.1" y="11.8" width="2.5" height="6.2" rx="1.25" fill="#fff" opacity="0.92" />
    </svg>
  );
}
