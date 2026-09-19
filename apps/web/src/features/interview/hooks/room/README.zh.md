# 面试房运行时 hooks

## 装配入口

`useInterviewRoom(sessionId)` 是唯一页面消费者;返回类型 `InterviewRoomModel` 是 UI 契约 SSOT。

## 子 hook 职责(装配顺序)

| Hook | 职责 |
| --- | --- |
| `useInterviewRoomBootstrap` | 会话元数据、历史消息、阶段恢复 |
| `useInterviewWS` | WebSocket 连接与 `TurnState` |
| `useInterviewRoomState` | UI 状态 + ref 容器 |
| `useInterviewRoomTtsBinding` | TTS 播放与生成对齐 |
| `useInterviewRoomSilenceTimer` | 沉默超时 / 追问 |
| `useInterviewRoomEvents` | WS 服务端事件处理 |
| `useInterviewRoomActions` | 用户操作(发送、收束、打断) |
| `useInterviewRoomRecorderBridge` | 麦克风 / 录音机桥接 |

## 跨 hook 数据流

- **State**:`useInterviewRoomState` 的 `state` + `set` + `refs`
- **WS**:`useInterviewWS` 的 `send` / `on`;经 `sendRef` 注入子 hook 以避免过期闭包
- **Recorder**:`recorderRef` 由 actions 与 recorder bridge 共享

新增 UI 行为时优先:

1. 决定归属哪个子 hook(不要把逻辑堆进 `useInterviewRoom`);
2. 需要新 ref 时,加到 `useInterviewRoomState`;
3. 仅在页面需要时才在 `InterviewRoomModel` 上暴露字段。

## 变更半径目标

单场景改动(如 TTS、沉默计时)应保持在 1–2 个 hook 文件内。
