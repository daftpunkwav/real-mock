/**
 * Shared mouth-shape math for both avatar renderers (3D talkinghead and the
 * 2D SVG portrait). Single source of truth so the two channels can never drift
 * apart again (the curve used to be hand-copied in each renderer).
 *
 * Pure functions only — unit-testable, no React, no WebGL.
 */

/** Silence floor: levels below this keep the mouth fully closed. */
export const MOUTH_LEVEL_FLOOR = 0.03;

/** Shaped level that maps to the widest mouth opening. */
export const MOUTH_LEVEL_CEILING = 0.75;

/** Max mouth opening (leave a little headroom so the jaw never looks broken). */
export const MOUTH_OPEN_MAX = 0.95;

/** Volume → mouth opening. Low level forces a closed mouth. */
export function mouthOpenFromLevel(level: number, speaking: boolean): number {
  if (!speaking) return 0;
  if (level < MOUTH_LEVEL_FLOOR) return 0;
  const shaped = Math.pow(
    Math.min(1, (level - MOUTH_LEVEL_FLOOR) / MOUTH_LEVEL_CEILING),
    0.85,
  );
  return Math.min(MOUTH_OPEN_MAX, 0.12 + shaped * 0.88);
}

/**
 * Per-syllable mouth colouring: real speech alternates wide/rounded lip
 * shapes syllable by syllable; a single open scalar reads as a puppet. The
 * phase advances with a syllable-rate clock (see `advanceSyllablePhase`),
 * energy modulates how strongly the shape deviates from neutral.
 */
export interface MouthShape {
  /** >0 stretches the mouth horizontally (spread "ee"-like). */
  wide: number;
  /** >0 rounds and purses the mouth ("oo"-like). */
  round: number;
}

export function syllableShape(phase: number, energy: number): MouthShape {
  if (energy <= 0.15) return { wide: 0, round: 0 };
  // Slow sine chooses the shape family; a second harmonic keeps successive
  // syllables from looking mechanically identical.
  const wave = Math.sin(phase) * 0.6 + Math.sin(phase * 2.7 + 1.3) * 0.4;
  const strength = Math.min(1, energy) * 0.45;
  if (wave >= 0) {
    return { wide: wave * strength, round: 0 };
  }
  return { wide: 0, round: -wave * strength };
}

/**
 * Advance the syllable-phase clock. Rate follows the voice's energy so a
 * calm sentence gets fewer, slower mouth-shape changes than an animated one.
 */
export function advanceSyllablePhase(phase: number, energy: number, dtMs: number): number {
  const hz = 4.5 + Math.min(1, energy) * 3.5;
  return phase + (dtMs / 1000) * hz * Math.PI * 2;
}

/** Smoothed signal follower: fast attack, slow release (per-frame, dt-normalized). */
export function followSignal(current: number, target: number, dtMs: number): number {
  const attack = 0.45;
  const release = 0.18;
  // The original constants were tuned for a 60fps rAF tick; keep the same
  // perceived speed at other frame rates.
  const k = (target > current ? attack : release) * Math.min(2, dtMs / 16.7);
  const next = current + (target - current) * k;
  return Math.abs(next - target) < 0.008 ? target : next;
}
