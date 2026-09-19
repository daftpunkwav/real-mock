# media/recorder/

面试房的麦克风采集:WebAudio 采集循环、VAD / 打断检测、PCM 缓冲、ASR 会话衔接。

| 模块 | 用途 |
| --- | --- |
| `useAudioRecorder.ts` | 采集状态机的主录音 hook |
| `useRecorderMicBootstrap.ts` | 麦克风引导(权限 / 设备初始化) |
| `useRecorderCaptureArm.ts` | 以环形缓冲种子与延迟 ASR 启动的方式布防采集 |
| `recorderMediaGraph.ts` | AudioContext + ScriptProcessor 音频图 |
| `recorderAudioFrame.ts` | 逐帧处理:VAD、打断检测、PCM 采集、静音提交 |
| `audioRecorderPcm.ts` | PCM 助手:语言占比、重采样、环形裁剪、编码、提交判定 |
| `audioRecorderConstants.ts` | 录音 / VAD / 打断阈值 |
| `audioRecorderAsr.ts` | ASR 会话与录音机共享的 ref 与回调 |
| `audioRecorderTypes.ts` | Web Speech API 类型 |
| `recorderInternalRefs.ts` | 录音 hook 的共享 ref 容器 |

TTS 播放在上一级(`useTTSPlayer*.ts`、`ttsAudio.ts`);本目录只管采集侧。
