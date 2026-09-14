/** TTS AudioContext and analyser helpers for playback level metering. */

/** Create AudioContext, or null when unsupported. */
export function createAudioContext(): AudioContext | null {
  try {
    return new AudioContext();
  } catch {
    return null;
  }
}

/** Resume a suspended context and report running state. */
export async function ensureContextRunning(ctx: AudioContext): Promise<boolean> {
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      return false;
    }
  }
  return ctx.state === "running";
}

/** Create an analyser node wired to the destination. */
export function createAnalyserNode(ctx: AudioContext): AnalyserNode | null {
  try {
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(ctx.destination);
    return analyser;
  } catch {
    return null;
  }
}

/** Link an audio element source into the analyser. */
export function connectElementToAnalyser(
  ctx: AudioContext,
  audio: HTMLAudioElement,
  analyser: AnalyserNode | null,
): MediaElementAudioSourceNode | null {
  if (!analyser) return null;
  try {
    const src = ctx.createMediaElementSource(audio);
    src.connect(analyser);
    return src;
  } catch {
    return null;
  }
}

/** Play a silent probe to unlock audio output. */
export function fireSilentProbe(ctx: AudioContext): void {
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    gain.gain.value = 0;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.02);
  } catch {
    /* noop */
  }
}
