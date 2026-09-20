# 前端

`apps/web` 下的 Next.js + React 应用。dev server 运行在 8080 端口且保持 dev 模式（`npm run dev`）；生产构建仅供 CI 使用。命令与完整源码布局见 [apps/web/README.md](../../apps/web/README.md)。

## 页面（`src/app/`）

一路由段一页。

| 路由段 | 页面 |
| --- | --- |
| `page.tsx` | 首页 |
| `profile/` | 候选人资料编辑器 |
| `resume/` | 简历列表 / 上传 / 深度评审；`resume/preview/` 为服务端渲染的预览页 |
| `settings/` | 设置 |
| `prep/` | Prep 教练对话 |
| `interview/` | 面试配置页(选项、模型绑定、多轮开关;`useInterviewSetup`) |
| `interview/[id]/` | 面试房间 |
| `report/[id]/` | 报告查看 |
| `history/` | 面试历史 |
| `growth/` | 成长统计 |
| `avatar-debug/` | 数字人调试页 |

外壳文件：`layout.tsx`（根布局）、`error.tsx`、`loading.tsx`、`not-found.tsx`、`globals.css`。

## Feature 模块（`src/features/`）

Feature-first 业务模块；每个 feature 自持组件、hook 与测试。跨 feature 的代码上移到 `src/components/` 与 `src/lib/`。见 [src/features/README.md](../../apps/web/src/features/README.md)。

| Feature | 用途 |
| --- | --- |
| `home/` | 落地页 |
| `profile/` | 候选人资料编辑器 |
| `resume/` | 简历上传、评审、分页预览 |
| `settings/` | 设置页（供应商、模型、阶段、集成） |
| `prep/` | Prep 教练对话 UI（输入区、上下文面板、斜杠命令） |
| `interview/` | 面试房间；房间 hook 装配在 `interview/hooks/room/` 有独立 README |
| `report/` | 报告展示（标签页、分数格式化、实时事件） |
| `history/` | 面试历史页 |
| `growth/` | 成长统计页 |
| `media/` | 共享媒体基础件：麦克风采集器（`recorder/`）、TTS 播放器 |
| `avatar/` | 面试官数字人渲染（舞台、立绘、场景） |

## i18n（`src/i18n/`）

语言为 `zh-CN` 与 `en`（`locales.ts`）；产品默认语言为 `en`。

| 模块 | 用途 |
| --- | --- |
| `LocaleProvider.tsx` / `localeContext.ts` | 语言状态；文档标题在此以 React `<title>` 渲染，不走 `document.title` |
| `storage.ts` | 语言持久化：localStorage 供客户端读取，同时写 cookie 以便服务端 SSR 出正确语言 |
| `locales.ts` / `resolve.ts` | 语言列表与解析 |
| `catalog.ts` | 文案目录的类型与查找 |
| `messages/` | 按语言划分的文案目录（`zh-CN/`、`en/`）——唯一允许存放用户可见文案之处 |
| `errors.ts` | `ApiError` → 本地化文案；错误码命中 `errors` 目录 |
| `format.ts` | 按语言格式化的工具函数 |
| `LocaleToggle.tsx` | 语言循环切换控件 |
| `localeInitScript.ts` | 注入文档的注水前语言引导脚本 |

错误码：`A` 族条目镜像后端 `realmock/platform/core/errors.py` 目录；`NET0000`–`NET0005` 族与 `http_*` 兜底覆盖网络层，由前端自持。

## 静态配置（`src/config/`）

| 文件 | 用途 |
| --- | --- |
| `nav.ts` | 导航 |
| `pageLayout.ts` | 页面布局 |
| `phases.ts` | 面试阶段英文标签；镜像后端 `realmock.domains.interview.workflows`（PhaseDef）——由 `apps/api/tests/interview/test_phase_ssot.py` 断言一致，phase id 不手工编辑 |
| `prepPrompts.ts` | Prep 快捷提示词 |

## API 契约类型（`src/types/generated/`）

`api.d.ts` 由后端 OpenAPI 契约生成。`npm run generate:api-types` 先运行 `../../scripts/export_openapi.py`，再对根目录 `openapi.json` 运行 `openapi-typescript`。该文件禁止手改。

## 浏览器内代码执行（`src/lib/code-runner/`）

| 语言 | 引擎 |
| --- | --- |
| `python` | Skulpt（浏览器内解释器），vendored 于 `public/vendor/skulpt`（锁定 1.2.0，无 CDN）；因 `Sk.configure` 依赖全局状态，运行串行执行；`execLimit` 限制 CPU 并抛出 `TimeLimitError` |
| `javascript` | 代码片段在 Blob Web Worker 中脱离 UI 线程运行；源码经 `postMessage` 传入，主线程计时器超时后终止 worker |
| `typescript` / `tsx` | sucrase 剥离类型（经动态 import 按需加载），随后交给 JavaScript worker 执行；`imports` transform 将 `import`/`export` 降级为 CJS shim |

`registry.ts` 将围栏语言 id 映射到引擎，别名 `js` / `ts` / `py`；UI 代码只调用 `isRunnable` / `getRunner`。

## 面试房运行时 hook 装配（`src/features/interview/hooks/room/`）

`useInterviewRoom(sessionId)` 是唯一的页面消费入口；其返回类型 `InterviewRoomModel` 为 UI 契约 SSOT。

| 子 hook | 职责 |
| --- | --- |
| `useInterviewRoomBootstrap` | 会话元数据、历史消息、阶段恢复 |
| `useInterviewWS` | WebSocket 连接与 `TurnState` |
| `useInterviewRoomState` | UI 状态 + ref 容器 |
| `useInterviewRoomTtsBinding` | TTS 播放与生成对齐 |
| `useInterviewRoomSilenceTimer` | 沉默超时 / 提示 |
| `useInterviewRoomEvents` | WS 服务端事件处理 |
| `useInterviewRoomActions` | 用户操作（发送、收尾、barge-in） |
| `useInterviewRoomRecorderBridge` | 麦克风 / 采集器桥接 |

细节与改动半径规则见 [src/features/interview/hooks/room/README.md](../../apps/web/src/features/interview/hooks/room/README.md)。

## 媒体采集（`src/features/media/recorder/`）

面试房间的麦克风采集：WebAudio 采集环路、VAD / barge-in 检测、PCM 缓冲、ASR 会话管线。`useAudioRecorder.ts` 持有采集状态机；`recorderMediaGraph.ts` 构建 `AudioContext` + `ScriptProcessor` 图；`recorderAudioFrame.ts` 负责逐帧 VAD、barge-in 检测、PCM 采集与静默提交。TTS 播放在上一层 `features/media/`。
