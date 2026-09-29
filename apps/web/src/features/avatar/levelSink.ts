/**
 * Module-level TTS level sink: the audio meter publishes every rAF frame and
 * the avatar renderers read the latest value inside their own animation loops.
 *
 * This bypasses React state on purpose: pumping a 60fps level through
 * setState re-rendered the whole interview room (chat included) every frame
 * and added a commit's worth of lip-sync latency. Listeners are for side
 * effects only; renderers should prefer `currentTTSLevel()` inside their rAF.
 */

type LevelListener = (level: number) => void;

let latest = 0;
const listeners = new Set<LevelListener>();

/** Publish a new TTS playback level (0..1). Called by the level loop. */
export function publishTTSLevel(level: number): void {
  latest = Math.max(0, Math.min(1, level));
  for (const fn of listeners) {
    try {
      fn(latest);
    } catch {
      /* a broken listener must not kill the meter */
    }
  }
}

/** Latest published level (0 when silent / not yet published). */
export function currentTTSLevel(): number {
  return latest;
}

/** Subscribe to level updates; returns an unsubscribe function. */
export function subscribeTTSLevel(fn: LevelListener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Drop every listener and reset the level (test / unmount helper). */
export function resetTTSLevelSink(): void {
  latest = 0;
  listeners.clear();
}
