# media/recorder/

Mic capture for the interview room: WebAudio capture loop, VAD / barge-in detection, PCM buffering, ASR-session plumbing.

| Module | Purpose |
| --- | --- |
| `useAudioRecorder.ts` | Main recorder hook owning the capture state machine |
| `useRecorderMicBootstrap.ts` | Microphone bootstrap (permission / device init) |
| `useRecorderCaptureArm.ts` | Arms capture with ring seed and delayed ASR start |
| `recorderMediaGraph.ts` | AudioContext + ScriptProcessor graph |
| `recorderAudioFrame.ts` | Per-frame processing: VAD, barge-in detection, PCM capture, silence commits |
| `audioRecorderPcm.ts` | PCM helpers: language ratio, resampling, ring trimming, encoding, commit checks |
| `audioRecorderConstants.ts` | Recorder / VAD / interruption thresholds |
| `audioRecorderAsr.ts` | Refs and callbacks shared by the ASR session and the recorder |
| `audioRecorderTypes.ts` | Web Speech API typings |
| `recorderInternalRefs.ts` | Shared ref container for the recorder hooks |

TTS playback lives one level up (`useTTSPlayer*.ts`, `ttsAudio.ts`); this directory is capture-side only.
