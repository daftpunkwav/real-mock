# lib/

跨 feature 共享的无框架依赖工具。

| 模块 / 目录 | 用途 |
| --- | --- |
| `api/` | HTTP 客户端栈:request / SSE 核心(`apiRequest.ts`、`apiSse.ts`、`apiUrl.ts`、`apiError.ts`、`base.ts`)与按域客户端(`*Http.ts`、`clients.ts`、`contract.ts`) |
| `code-runner/` | 浏览器内代码执行:`pythonRunner.ts`(Skulpt)、`javascriptRunner.ts`(Blob Worker)、`typescriptRunner.ts`(类型剥离),及 `registry.ts` / `output.ts` / `types.ts` |
| `cnText.ts` | 中文文本助手(面向存量评价数据的全角标点归一化) |
| `thinkStream.ts` | 将流式内容拆分为思考过程与最终回答(`<think>` / `<thinking>` 标签形态) |
| `interviewProcesses.ts` | 多轮面试流程续接的纯函数助手(无 React / 无 API) |
| `compactThreshold.ts` | Prep 压缩偏好(localStorage 存储:触发阈值、压缩强度、压缩指令、逐字保留窗口) |
| `canonicalHost.ts` | 水合前脚本,将回环主机固定为 127.0.0.1(避免主机绑定的 cookie 使会话失联) |
| `askDialog.ts` / `askTimeout.ts` | ask_user 弹窗助手:SSE 事件归一化、答案格式化、超时处理 |
| `clipboard.ts` / `download.ts` | 剪贴板与文件下载助手 |
| `llmDefaults.ts` / `scoreColor.ts` / `env.ts` / `utils.ts` | 小型单一用途助手 |
