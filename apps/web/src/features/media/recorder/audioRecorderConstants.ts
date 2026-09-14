/** Recorder, VAD, and interruption thresholds. */

/** Cap long-session chunks at 30 MB by dropping the oldest chunk. */
export const MAX_CHUNKS_BYTES = 30 * 1024 * 1024;
/** Minimum chunk count before silence can end a turn. */
export const MIN_CHUNKS_BEFORE_SILENCE = 2;
/** Default silence window, long enough to preserve thinking pauses. */
export const SILENCE_TRIGGER_MS = 1800;
/** Fast path after a recent final result and settled punctuation/interim text. */
export const SILENCE_FAST_MS = 1000;
/** RMS values below this threshold count as silence. */
export const SILENCE_RMS_THRESHOLD = 0.006;
/** Higher interruption threshold to avoid speaker echo and ambient noise. */
export const BARGE_RMS_THRESHOLD = 0.028;
/** Sustained high-energy duration required for an interruption candidate. */
export const BARGE_SUSTAIN_MS = 700;
/** Require roughly 1.2 seconds of speech energy (4096@16k is about 256 ms/chunk). */
export const MIN_SPEECH_CHUNKS = 5;
/** Sufficient text can relax the speech-energy requirement. */
export const MIN_TEXT_CHARS = 8;
/** Do not commit while interim recognition is still updating. */
export const INTERIM_ACTIVE_MS = 600;
/** Stability window after a final result clears interim text. */
export const FINAL_SETTLE_MS = 400;
/** Throttle speech activity callbacks used by silence nudges, not interruptions. */
export const SPEECH_ACTIVITY_THROTTLE_MS = 400;
export const TARGET_SAMPLE_RATE = 16000;
/** Ring-buffer duration during AI speech, reused when an interruption begins. */
const RING_BUFFER_SEC = 2.5;
export const RING_BUFFER_MAX_BYTES = Math.floor(TARGET_SAMPLE_RATE * 2 * RING_BUFFER_SEC);

/** Brief quiet period before capture starts to avoid speaker tail audio. */
export const CAPTURE_ARM_DELAY_MS = 450;
/** Shorter arm delay after interruption because the ring buffer includes trigger audio. */
export const CAPTURE_ARM_AFTER_BARGE_MS = 200;

export const SENTENCE_END_RE = /[\u3002\uFF01\uFF1F.!?]$/;
