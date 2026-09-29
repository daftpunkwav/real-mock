/** rAF level loop sampling the analyser for TTS playback levels. */

export interface TTSLevelLoop {
  start(): void;
  stop(): void;
}

/**
 * Automatic gain control: normalize RMS against a decaying peak so quiet and
 * loud voices both use the full 0..1 meter range. The peak also decays
 * through silence, so the meter recovers between utterances.
 *
 * This is the shipped path — the level loop calls it every frame; keep any
 * tuning change here covered by the unit tests.
 *
 * @param rms Current frame RMS (0..1).
 * @param peak Mutable running-peak holder owned by the caller.
 * @param decayPerFrame Peak multiplier for this frame; the loop passes a
 *   dt-rescaled value so the release speed is refresh-rate independent
 *   (0.9985 ≈ halving the peak every ~8s at 60fps).
 */
export function agcNormalize(
  rms: number,
  peak: { value: number },
  decayPerFrame = 0.9985,
): number {
  peak.value = Math.max(rms, peak.value * decayPerFrame);
  if (rms <= 0.0005) return 0;
  const floor = 0.08; // silence guard: never divide into huge gains
  return Math.min(1, rms / Math.max(floor, peak.value));
}

export function createTTSLevelLoop(opts: {
  getAnalyser: () => AnalyserNode | null;
  onLevel: (level: number) => void;
}): TTSLevelLoop {
  let raf: number | null = null;
  const peak = { value: 0 };
  let lastMs = 0;

  const stop = () => {
    if (raf != null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    peak.value = 0;
    opts.onLevel(0);
  };

  const start = () => {
    const analyser = opts.getAnalyser();
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = ((data[i] ?? 128) - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      // Rescale the peak decay to a constant reference frame time so the
      // release speed does not depend on display refresh rate.
      const now = typeof performance === "undefined" ? 0 : performance.now();
      const dt = lastMs ? Math.min(200, now - lastMs) : 16.7;
      lastMs = now;
      const decayPerFrame = Math.pow(0.9985, dt / 16.7);
      opts.onLevel(agcNormalize(rms, peak, decayPerFrame));
      raf = requestAnimationFrame(tick);
    };
    stop();
    lastMs = 0;
    raf = requestAnimationFrame(tick);
  };

  return { start, stop };
}
