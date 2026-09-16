/** Countdown display helpers for the think/answer turn timer. */

/** Format remaining seconds for the chat-panel timer chip (e.g. "45s", "2:05"). */
export function formatTurnCountdown(totalSec: number): string {
  const s = Math.max(0, Math.ceil(totalSec));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
