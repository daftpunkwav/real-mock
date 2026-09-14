/** PCM helpers for language ratio, resampling, ring trimming, encoding, and commit checks. */
import {
  TARGET_SAMPLE_RATE,
  MAX_CHUNKS_BYTES,
  MIN_CHUNKS_BEFORE_SILENCE,
  SILENCE_TRIGGER_MS,
  SILENCE_FAST_MS,
  MIN_SPEECH_CHUNKS,
  MIN_TEXT_CHARS,
  INTERIM_ACTIVE_MS,
  FINAL_SETTLE_MS,
  SENTENCE_END_RE,
} from "./audioRecorderConstants";

/** Estimate the Latin-letter ratio used to choose the recognition language. */
export function latinLetterRatio(text: string): number {
  const letters = text.replace(/[^A-Za-z\u4e00-\u9fff]/g, "");
  if (!letters.length) return 0;
  const latin = (letters.match(/[A-Za-z]/g) || []).length;
  return latin / letters.length;
}

/** Close an AudioContext safely without duplicate-close InvalidStateError failures. */
export function safeCloseAudioContext(ctx: AudioContext | null) {
  if (ctx && ctx.state !== "closed") {
    void ctx.close().catch(() => {});
  }
}

/** Resample Int16 PCM to 16 kHz for STT upload. */
function downsampleTo16k(input: Int16Array, inputRate: number): Int16Array {
  if (!input.length || inputRate === TARGET_SAMPLE_RATE) return input;
  if (inputRate < 8000) return input;
  const ratio = inputRate / TARGET_SAMPLE_RATE;
  const outLen = Math.max(1, Math.floor(input.length / ratio));
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    out[i] = input[Math.min(input.length - 1, Math.floor(i * ratio))] ?? 0;
  }
  return out;
}

/** Drop chunks from the front until the byte limit is satisfied. */
export function trimRing(
  chunks: Int16Array[],
  bytesRef: { current: number },
  maxBytes: number,
) {
  while (chunks.length > 1 && bytesRef.current > maxBytes) {
    const dropped = chunks.shift();
    if (dropped) bytesRef.current -= dropped.byteLength;
  }
}

/** Convert Float32 samples to Int16 PCM. */
export function floatTo16BitPCM(float32: Float32Array): Int16Array {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i] ?? 0));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Merge chunks, resample to 16 kHz, and encode as base64. */
export function encodeBase64(arrays: Int16Array[], sampleRate: number): string {
  if (!arrays.length) return "";
  const total = arrays.reduce((s, a) => s + a.length, 0);
  const merged = new Int16Array(total);
  let offset = 0;
  for (const a of arrays) {
    merged.set(a, offset);
    offset += a.length;
  }
  const pcm16k = downsampleTo16k(merged, sampleRate);
  const bytes = new Uint8Array(pcm16k.buffer, pcm16k.byteOffset, pcm16k.byteLength);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i] ?? 0);
  return btoa(binary);
}

/** Append a chunk and discard the oldest data when the cap is exceeded. */
export function appendChunkWithCap(
  chunks: Int16Array[],
  bytesRef: { current: number },
  pcm: Int16Array,
) {
  chunks.push(pcm);
  bytesRef.current += pcm.byteLength;
  while (chunks.length > 1 && bytesRef.current > MAX_CHUNKS_BYTES) {
    const dropped = chunks.shift();
    if (dropped) bytesRef.current -= dropped.byteLength;
  }
}

/** Recorder state required for a silence commit decision. */
interface CommitCheckState {
  silenceStartMs: number | null;
  chunkCount: number;
  speechChunks: number;
  finals: string;
  interim: string;
  lastInterimUpdate: number;
  lastFinalAt: number;
}

/** Decide whether silence, speech, text, and punctuation are sufficient to commit. */
export function shouldCommitOnSilence(state: CommitCheckState): boolean {
  if (!state.silenceStartMs) return false;
  const silenceMs = Date.now() - state.silenceStartMs;
  if (state.chunkCount <= MIN_CHUNKS_BEFORE_SILENCE) return false;
  const text = `${state.finals}${state.interim}`.trim();
  const enoughSpeech = state.speechChunks >= MIN_SPEECH_CHUNKS || text.length >= MIN_TEXT_CHARS;
  if (!enoughSpeech) return false;

  // A recently updated interim result means the speaker may only be pausing briefly.
  if (state.interim && Date.now() - state.lastInterimUpdate < INTERIM_ACTIVE_MS) {
    return false;
  }

  const now = Date.now();
  const hasRecentFinal = state.lastFinalAt > 0 && now - state.lastFinalAt < 8000;
  const endsWithPunct = SENTENCE_END_RE.test(text);
  const interimEmptySettled =
    !state.interim && state.lastFinalAt > 0 && now - state.lastFinalAt >= FINAL_SETTLE_MS;
  const fastPath = hasRecentFinal && (endsWithPunct || interimEmptySettled);
  const threshold = fastPath ? SILENCE_FAST_MS : SILENCE_TRIGGER_MS;
  return silenceMs > threshold;
}
