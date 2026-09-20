# 更新日志

此处记录本项目用户可见的变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),版本号遵循语义化版本(SemVer)。

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
