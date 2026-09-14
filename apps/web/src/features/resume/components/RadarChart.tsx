"use client";

/**
 * @file RadarChart.tsx
 * @description SVG radar for equal-weight review dimensions.
 */

import { useT } from "@/i18n";
import { useInViewReveal } from "../useInViewReveal";

interface RadarDim {
  key: string;
  label: string;
  score: number;
}

const SIZE = 340;
const CENTER = SIZE / 2;
const RADIUS = 108;
const LEVELS = 4;

function pointAt(index: number, total: number, ratio: number): [number, number] {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  return [CENTER + RADIUS * ratio * Math.cos(angle), CENTER + RADIUS * ratio * Math.sin(angle)];
}

function polygonPoints(values: number[]): string {
  return values
    .map((v, i) => pointAt(i, values.length, Math.max(0.04, v / 100)).join(","))
    .join(" ");
}

function labelAnchor(index: number, total: number): "start" | "end" | "middle" {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  const cos = Math.cos(angle);
  if (cos > 0.35) return "start";
  if (cos < -0.35) return "end";
  return "middle";
}

/** Equal-weight SVG radar; optional overlays are prior versions. */
export function RadarChart({
  dims,
  overlays = [],
}: {
  dims: RadarDim[];
  overlays?: number[][];
}) {
  const t = useT("resume");
  const { ref, shown, reduce } = useInViewReveal();

  const n = dims.length;
  if (n < 3) return null;
  const values = dims.map((d) => Math.max(0, Math.min(100, d.score)));
  const gridRatios = Array.from({ length: LEVELS }, (_, i) => (i + 1) / LEVELS);

  return (
    <div ref={ref} className="flex justify-center" role="img" aria-label={t("radar.aria")}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="h-auto w-full max-w-[380px]"
        style={{ overflow: "visible" }}
      >
        {/* Concentric grid rings. */}
        {gridRatios.map((r) => (
          <polygon
            key={r}
            points={polygonPoints(Array(n).fill(r * 100))}
            fill="none"
            stroke="var(--border)"
            strokeWidth={1}
          />
        ))}
        {/* Note */}
        {dims.map((d, i) => {
          const [x, y] = pointAt(i, n, 1);
          return (
            <line
              key={d.key}
              x1={CENTER}
              y1={CENTER}
              x2={x}
              y2={y}
              stroke="var(--border)"
              strokeWidth={1}
            />
          );
        })}
        {/* Scale labels. */}
        {gridRatios.map((r) => (
          <text
            key={r}
            x={CENTER + 4}
            y={CENTER - RADIUS * r + 3}
            fontSize={8}
            fill="var(--muted-foreground)"
            opacity={0.65}
          >
            {r * 100}
          </text>
        ))}
        {overlays.map((overlay, oi) => (
          <polygon
            key={`overlay-${oi}`}
            points={polygonPoints(overlay.map((v) => Math.max(0, Math.min(100, v))))}
            fill="none"
            stroke="var(--muted-foreground)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            opacity={0.45}
          />
        ))}
        <polygon
          points={polygonPoints(values)}
          fill="color-mix(in srgb, var(--primary) 14%, transparent)"
          stroke="var(--primary)"
          strokeWidth={2}
          strokeLinejoin="round"
          style={{
            opacity: shown ? 1 : 0,
            transformOrigin: `${CENTER}px ${CENTER}px`,
            transform: shown ? "scale(1)" : "scale(0.25)",
            transition: "opacity 0.7s ease, transform 0.9s cubic-bezier(0.22, 1, 0.36, 1)",
          }}
        />
        {/* Dots and labels with staggered reveal. */}
        {dims.map((d, i) => {
          const [x, y] = pointAt(i, n, Math.max(0.04, values[i]! / 100));
          const [lx, ly] = pointAt(i, n, 1.22);
          const delay = reduce ? 0 : 0.45 + i * 0.06;
          return (
            <g key={d.key}>
              <circle
                cx={x}
                cy={y}
                r={3.5}
                fill="var(--card)"
                stroke="var(--primary)"
                strokeWidth={2}
                style={{
                  opacity: shown ? 1 : 0,
                  transition: `opacity 0.35s ease ${delay}s`,
                }}
              />
              <text
                x={lx}
                y={ly}
                fontSize={11}
                fontWeight={500}
                fill="var(--foreground-muted)"
                textAnchor={labelAnchor(i, n)}
                dominantBaseline="middle"
                style={{
                  opacity: shown ? 1 : 0,
                  transition: `opacity 0.4s ease ${delay + 0.08}s`,
                }}
              >
                {d.label}
              </text>
              <text
                x={lx}
                y={ly + 13}
                fontSize={10}
                fontWeight={600}
                fill="var(--primary)"
                textAnchor={labelAnchor(i, n)}
                dominantBaseline="middle"
                className="num-tabular"
                style={{
                  opacity: shown ? 0.9 : 0,
                  transition: `opacity 0.4s ease ${delay + 0.14}s`,
                }}
              >
                {values[i]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
