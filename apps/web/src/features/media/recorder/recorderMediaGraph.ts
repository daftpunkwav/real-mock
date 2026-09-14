/** AudioContext + ScriptProcessor . */

import { TARGET_SAMPLE_RATE } from "./audioRecorderConstants";
import type { RecorderFrameRefs } from "./recorderAudioFrame";
import { processRecorderAudioFrame } from "./recorderAudioFrame";

export function attachRecorderProcessor(
  ctx: AudioContext,
  source: MediaStreamAudioSourceNode,
  frameSession: number,
  getActiveSession: () => number,
  refs: RecorderFrameRefs,
): ScriptProcessorNode {
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    processRecorderAudioFrame(input, frameSession, getActiveSession(), refs);
  };
  source.connect(processor);
  const silent = ctx.createGain();
  silent.gain.value = 0;
  processor.connect(silent);
  silent.connect(ctx.destination);
  return processor;
}

export async function openMicStream(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
}

export async function createRecorderAudioContext(stream: MediaStream): Promise<{
  ctx: AudioContext;
  source: MediaStreamAudioSourceNode;
}> {
  const ctx = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  const source = ctx.createMediaStreamSource(stream);
  return { ctx, source };
}
