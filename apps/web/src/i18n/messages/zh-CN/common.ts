/** 通用文案:动作、状态、壳层控件(主题/语言切换)的 label。 */

export const common = {
  "action.confirm": "确定",
  "action.cancel": "取消",
  "action.retry": "重试",
  "action.copy": "复制",
  "action.close": "关闭",
  "action.save": "保存",
  "action.delete": "删除",
  "action.edit": "编辑",
  "action.test": "测试",
  "state.loading": "加载中…",
  "state.saving": "保存中…",
  "state.empty": "暂无内容",
  "state.error": "出错了",
  "request.failed": "请求失败: {status}",
  "stream.failed": "流式输出失败",
  "theme.light": "浅色",
  "theme.dark": "深色",
  "theme.system": "跟随系统",
  "theme.toggle.title": "主题:{label}(点击切换)",
  "theme.toggle.aria": "当前主题 {label},点击切换",
  "locale.toggle.title": "界面语言:{label}(点击切换)",
  "locale.toggle.aria": "当前界面语言 {label},点击切换",

  // 共享组件层(Toast/ConfirmDialog/LoadError/ModelSelect/ContextGauge/Sidebar/边界页)

  // 动作补充(err 与 not-found 共用的返回首页;Toast 关闭复用 action.close)
  "action.backHome": "返回首页",

  // ConfirmDialog 默认按钮
  "confirm.confirm": "确认",
  "confirm.cancel": "取消",

  // LoadError
  "load.failed": "加载失败",
  "load.hint.notConfigured": "（未配置）",
  "load.hint.checkEnv": "请检查 NEXT_PUBLIC_* 环境变量",
  "load.backendHintPrefix": "请确认后端已启动(当前配置:",
  "load.backendHintSuffix": ")。若刚改过端口,请重启 frontend。",

  // ModelSelect / EffortSelect
  "model.effort.low": "低",
  "model.effort.medium": "中",
  "model.effort.high": "高",
  "model.effort.max": "最高",
  "model.effort.aria": "思考强度",
  "model.notSet": "未设置",
  "model.useDefault": "默认（{label}）",

  // ContextGauge
  "context.usage": "上下文使用 {percent}",
  "context.usageAria": "上下文使用情况",
  "context.panel.title": "上下文容量",
  "context.panel.usage": "{used}/{total}（{percent}）",
  "context.panel.usageNoModel": "{used}（未选模型）",
  "context.noMessages": "暂无消息",
  "context.promptTokens": "输入 token",
  "context.completionTokens": "输出 token",
  "context.cacheRate": "缓存命中率",
  "context.cacheRateValue": "{percent}（{tokens}）",
  "context.estimated": "估算",
  "context.estimatedHint": "服务商未上报输入用量,按上下文实测估算,仅供参考",
  "context.bucket.user": "用户消息",
  "context.bucket.userHint": "你发送的消息正文",
  "context.bucket.assistant": "助手回复",
  "context.bucket.assistantHint": "模型最终回复正文,不含推理与工具内容",
  "context.bucket.thinking": "推理思考",
  "context.bucket.thinkingHint": "模型的思考过程,按输出计费",
  "context.bucket.tools": "工具与检索",
  "context.bucket.toolsHint": "工具调用、检索结果与执行记录",
  "context.bucket.system": "系统提示词",
  "context.bucket.systemHint": "教练人设、简历/公司上下文与语言规则",
  "context.bucket.memory": "记忆与摘要",
  "context.bucket.memoryHint": "长期记忆索引、压缩摘要与引用会话",
  "context.bucket.other": "其他",
  "context.bucket.otherHint": "未分类的上下文内容",

  // Sidebar
  "sidebar.openNav": "打开导航",
  "sidebar.closeNav": "关闭导航",
  "sidebar.expand": "展开侧栏",
  "sidebar.collapse": "收起侧栏",
  "sidebar.resize": "拖动调整侧栏宽度",

  // not-found 页
  "nf.title": "找不到该页面",
  "nf.description": "你访问的链接可能已被删除、合并,或者从来没有过。",

  // error boundary 页
  "err.eyebrow": "Error",
  "err.title": "页面出现异常",
  "err.unknown": "未知错误,请稍后再试。",
  "err.trace": "trace: {digest}",

  // 代码块
  "code.plain": "纯文本",
  "code.copy": "复制",
  "code.copied": "已复制",
  "code.run": "运行",
  "code.stop": "停止",
  "code.running": "运行中…",
  "code.output": "输出",
  "code.status.ok": "完成",
  "code.status.error": "出错",
  "code.status.timeout": "超时",
  "code.status.cancelled": "已取消",
  "code.status.unavailable": "不可用",
  "code.durationMs": "{ms} ms",
  "code.truncated": "输出过长已截断",
  "code.closeOutput": "关闭输出",
  "code.diagram": "图表",
  "code.source": "源码",
  "code.zoomIn": "放大",
  "code.zoomOut": "缩小",
  "code.zoomReset": "重置为 100%",
  "code.fullscreen": "全屏查看",
  "code.diagramFailed": "图表解析失败，已显示源码",
  "code.errorDetail": "技术细节",
} as const;

export type CommonMessageKey = keyof typeof common;
