/** rAF level loop sampling the analyser for TTS playback levels. */

export interface TTSLevelLoop {
  start(): void;
  stop(): void;
}

export function createTTSLevelLoop(opts: {
  getAnalyser: () => AnalyserNode | null;
  onLevel: (level: number) => void;
}): TTSLevelLoop {
  let raf: number | null = null;

  const stop = () => {
    if (raf != null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
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
      opts.onLevel(Math.min(1, rms * 4));
      raf = requestAnimationFrame(tick);
    };
    stop();
    raf = requestAnimationFrame(tick);
  };

  return { start, stop };
}
