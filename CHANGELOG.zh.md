# 更新日志

此处记录本项目用户可见的变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),版本号遵循语义化版本(SemVer)。

## [未发布]

### 新增

- Agent 韧性:LLM 调用按 10 级梯度重试并遵循供应商 `Retry-After`;工具对瞬态失败自动重试两次,每工具有独立默认超时且模型可按次延长;熔断计数写入每次失败观测,模型能看到距离熔断还剩几次
- Agent 感知:每次请求注入一份瞬态当前日期时间;每轮注入预算行(轮数/宽度/已消耗次数);被输出上限截断的最终答案自动无缝续写一次,仍截断则显式标记
- 思考档位:模型可声明自定义档位列表(`extras.reasoning.variants`)并逐字传给供应商,Anthropic 按档位插值预算,未设置时使用默认档;思考强度选择器跟随所选模型
- Prep 工具:`web_fetch` 按需读取搜索命中的页面全文;`web_search` 暴露 `max_results`
- 长期记忆:轮末一次咨询式判定本 turn 是否值得沉淀(至多写一条);Prep 设置新增记忆索引注入条数(0 = 全部)
- 上下文压缩:折叠轮次保留确定性工具调用登记册(工具/参数/结果摘要/引用 URL),摘要器以更大预算读取工具观察
- 上下文面板:供应商请求诊断(请求数、请求 id、耗时、reasoning token、最近错误)

### 修复

- 供应商响应:结束原因与业务错误体(如 MiniMax `base_resp`)不再被静默吞掉——截断答案续写并标记、refusal 文本正常显示、上游错误脱敏后原样上屏而非笼统文案
- 流式:三种协议均在首个增量前重试,供应商终态错误事件抛出而非静默结束,兼容无空格的 SSE `data:` 行
- Anthropic 开思考的工具循环按官方要求回传带签名的思考块
- MiniMax chat:播种条目自动请求 `reasoning_split`,思考内容才能真正返回
- Prep 界面:markdown 表格中的行内代码不再从中间折行,思考/工具轨迹占满气泡宽度,上下文环弹层不再被裁剪
- Prep 上下文:思考过程落库移除仅用于展示的 2 万字符截断

## [0.1.0] - 2026-09-21

### 新增

- 简历域:上传与解析(含图片型 PDF 的视觉转写)、深度评价流水线(内容深读 / 市场对标 / 项目深挖 / 综合裁定)、服务端分页预览
- Prep 面试教练:agent 会话(工具调用、流式输出、会话记忆压缩)、职位调研资源
- 拟真面试房:WebSocket 实时对话、语音采集与播放、面试历史
- 模型能力体系:provider / channel / model 分表声明 + 模型级能力标记、task 绑定与场景覆盖
- 工程化:OpenAPI 契约流水线(`scripts/export_openapi.py` → `openapi.json` → 前端类型)、`scripts/dev.sh` 一键本地启动

### 修复

- Prep agent 健壮性:业务错误透传(不再被吞成空轮次)、整轮 600s 超时、工具压缩 30s 内收敛、取消轮次正确回收、断连感知与有界事件队列
- Prep 并发安全:DB 访问移出事件循环、`memory_write` 幂等(去重键 + 摘要级去重)与串行化写入
- Prep 上下文:system prompt 拆分为稳定优先的种子块、回复语言提示移至每轮后缀、摘要位置固定 — 提升提示词缓存命中率
- Prep 用量统计:流式 `usage` 按轮增量,`done`/sync 响应携带会话级三元组,前端增量合并 + 服务端自愈
- Prep 输入区容量:推理与工具载荷计入「system & tools」桶,本地消息不计入,未知的服务端部分归入 system 桶而非恒定 0%
- Prep 体验:输出中可切换模型与思考强度(按发送快照生效)、后台生成在会话列表可见且可单独停止、fork 归一化与分支计数重置
- Prep 上下文面板:服务端度量的七类分解(用户消息 / 助手回复 / 推理 / 工具与检索 / system prompt / 记忆与摘要 / 其他,悬停查看计量说明)、输入 token 缺失时的估算标记、缓存命中率仅由上报值计算
- Prep slash 命令:/compact(立即压缩并写摘要)、/clear(确认后清空)、/help(本地帮助)
- Prep # 引用:经输入区 # 菜单多选会话、chips 展示、仅注入当前轮(不持久化);移除右侧关联会话卡(后端 link 端点保留兼容)
- Markdown:代码块语言标签 + 一键复制、Mermaid 图渲染(解析失败回退为代码)、深色主题支持
- Markdown 代码高亮:prism 按需加载 20 种语言、明暗 token 配色、超大代码块降级为纯文本
- Markdown 代码运行器:python(skulpt 本地子集,execLimit 熔断)/ javascript(Blob Worker + 超时终止)/ typescript(sucrase 类型剥离后进 Worker);其他语言仅复制;输出面板区分 stdout/stderr/错误并显示截断提示
- Mermaid 体验:解析失败不再泄漏红色错误图(改为源码视图 + 温和提示)、图 / 源码双视图、50%–300% 缩放 + 全屏、深色主题配色、主题切换时重渲染
- Select 统一:全站原生 select 迁移为自定义 Select(键盘 / ARIA),覆盖面试设置与 Prep 相关表单
- 测试基建:vitest React 插件支持 .tsx 组件测试,补齐用例间缺失的 Select 清理

[0.1.0]: https://github.com/daftpunkwav/real-mock/releases/tag/v0.1.0
