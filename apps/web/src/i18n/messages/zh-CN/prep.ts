/** prep 文案(zh-CN 为 key 源;key 用点分路径,zh 值从源码逐字迁移)。 */

export const prep = {
  // 页面头部
  "page.eyebrow": "Prep Coach",
  "page.title": "面试准备",

  // 聊天区(页面级按钮 / 错误行 / 思考过程)
  "chat.dismissError": "关闭错误提示",
  "chat.jumpToBottom": "回到底部",
  "chat.sendFailedFallback": "失败",
  "chat.replyInterrupted": "回复中断:{reason}",
  "chat.replyError": "错误:{reason}",

  // 输入条
  "composer.placeholder": "问我任何面试相关问题…",
  "composer.placeholderQueued": "生成中,输入将排队发送…",
  "composer.compacting": "正在压缩上下文,请稍候…",
  "composer.multilineHint": "Enter 发送,Shift+Enter 换行",
  "composer.selectModel": "选择模型",
  "composer.send": "发送",
  "composer.refChips": "本次引用的会话",
  "composer.refRemove": "移除引用",
  "composer.refMenuTitle": "引用会话(仅本轮生效)",
  "composer.refMenuEmpty": "没有可引用的会话",

  // token 用量分项
  "tokens.gauge.messages": "消息",
  "tokens.gauge.replies": "回复",
  "tokens.gauge.system": "系统与工具",

  // 空态(开始辅导前)
  "empty.title": "开始你的面试辅导",
  "empty.desc": "关联简历后,AI 教练将基于你的背景进行针对性辅导。",
  "empty.resumeLabel": "关联简历",
  "empty.resumeActiveSuffix": " (投递)",
  "empty.noResume": "暂无简历,可先去「简历管理」上传,也可直接开始通用辅导",
  "empty.starting": "正在连接…",
  "empty.start": "开始辅导",

  // 会话列表
  "sessions.title": "对话记录",
  "sessions.new": "新对话",
  "sessions.empty": "暂无历史对话;发起第一条消息后自动保存",
  "sessions.genericGroup": "通用辅导",
  "sessions.newSessionFallback": "新会话",
  "sessions.messageCount": "{count} 条",
  "sessions.time.justNow": "刚刚",
  "sessions.time.minutesAgo": "{n} 分钟前",
  "sessions.time.hoursAgo": "{n} 小时前",
  "sessions.time.daysAgo": "{n} 天前",

  // 会话生命周期
  "sessions.welcome":
    "你好!我是你的面试准备教练。告诉我你的目标岗位,或让我帮你分析简历、出题练习。",
  "sessions.switchFailed": "切换会话失败:{reason}",
  "sessions.switchFailedFallback": "切换会话失败",
  "sessions.createFailed": "创建辅导会话失败",
  "sessions.backendDown": "后端无响应,请确认后端正在运行",
  "sessions.backendUnstable": "后端连接不稳定,已重试仍失败,请稍后再试",
  "sessions.delete": "删除",
  "sessions.generating": "正在生成,点击停止按钮可停止本会话的生成",
  "sessions.stopGeneration": "停止生成",
  "sessions.deleteTitle": "删除会话",
  "sessions.deleteBody": "确定删除该会话及其全部消息吗?此操作不可恢复。",
  "sessions.deleteFailed": "删除会话失败",
  "sessions.archive": "归档",
  "sessions.archiveTitle": "归档会话",
  "sessions.archiveBody": "归档后会话移入归档分组,仍可继续使用。",
  "sessions.archiveFailed": "归档操作失败",
  "sessions.unarchive": "取消归档",
  "sessions.unarchiveTitle": "取消归档",
  "sessions.unarchiveBody": "确定将该会话移回会话列表吗?",
  "sessions.clear": "清空消息",
  "sessions.clearTitle": "清空会话消息",
  "sessions.clearBody": "确定清空该会话的全部消息吗?此操作不可恢复。",
  "sessions.clearFailed": "清空消息失败",
  "sessions.cancelAction": "取消",
  "sessions.archivedTitle": "已归档 · {count}",
  "sessions.archivedBadge": "已归档",
  "sessions.linkTitle": "关联会话",
  "sessions.linkDesc": "选择一个会话,教练将在首轮读到它的目标与最近对话。",
  "sessions.linkPlaceholder": "选择要关联的会话…",
  "sessions.unlink": "取消关联",
  "sessions.linkFailed": "关联会话失败",

  // 检索卡片 / 简历加载
  "resources.sourcesSummary": "检索来源 · {total} 条 / {groups} 组",
  "resources.queryLabel": "查询:{query}",
  "resources.resumeLoadFailed": "简历列表加载失败",

  // 右侧栏
  "panel.resumeTitle": "关联简历",
  "panel.resumeActive": "当前投递",
  "panel.resumeInactive": "未设为投递",
  "panel.resumeScore": " · 评分 {score}",
  "panel.noResume": "未关联简历,将进行通用辅导",
  "panel.quickPrompts": "快捷提问",

  // 快捷提问(点击后写入输入框的完整句子)
  "quick.analyzeResume": "帮我分析简历的亮点与不足",
  "quick.techQuestions": "针对目标岗位出 5 道技术面试题",
  "quick.behavioralMock": "模拟一场行为面试并点评我的回答",
  "quick.searchExperiences": "搜索近期面经并总结高频考点",

  // Agent 工具名
  "agent.tool.webSearch": "搜索面经",
  "agent.tool.companyInfo": "查询公司",
  "agent.tool.quiz": "出练习题",
  "agent.tool.askUser": "向你提问",
  "agent.tool.takeNote": "记录要点",
  "agent.tool.memoryListTags": "查看记忆标签",
  "agent.tool.memoryListSummaries": "查看记忆摘要",
  "agent.tool.memoryGetDetail": "读取记忆详情",
  "agent.tool.memoryWrite": "写入长期记忆",
  "agent.tool.githubListRepos": "查看 GitHub 仓库",
  "agent.tool.githubGetReadme": "读取仓库 README",
  "agent.tool.githubGetRepo": "查看仓库详情",
  "agent.tool.githubListCommits": "查看提交记录",
  "agent.tool.githubGetUser": "查看 GitHub 用户",
  "agent.tool.compactContext": "压缩上下文",
  "agent.tool.searchTools": "搜索工具",

  // Agent 提问弹窗
  "ask.title": "教练想确认",
  "ask.customPlaceholder": "或输入自定义回答…",
  "ask.send": "发送回答",
  "ask.dismiss": "暂不回答,稍后在输入框回复",
  "ask.confirm": "确认",
  "ask.progress": "已回答 {answered}/{total}",
  "ask.multiHint": "可多选",
  "ask.recommended": "推荐",
  "ask.autoIn": "{time} 后自动选择「{choice}」",

  // 思考与执行时间线
  "trace.title": "思考与执行",
  "trace.rawName": "工具原名:",
  "trace.detailArgs": "调用参数",
  "trace.detailResult": "调用结果",

  // 消息操作
  "actions.copy": "复制",
  "actions.copyFailed": "复制失败",
  "actions.export": "导出为 Markdown",
  "actions.fork": "从此处派生新会话",
  "actions.forkFailed": "派生会话失败",
  "actions.regenerate": "重新生成",
  "actions.regenerateFailed": "找不到可重新生成的问题",
  "actions.regenerateLatestOnly": "只能重新生成最后一条回复",
  "actions.rate": "评价此回应",
  "actions.rateDone": "评价已保存为长期记忆",
  "actions.rateFailed": "保存评价失败",
  "actions.retract": "撤回此消息及后续",
  "actions.retractFailed": "撤回失败",

  // 停止与停止态
  "composer.stop": "停止生成",
  "chat.stopped": "已停止",
  "chat.stoppedEmpty": "已停止,未生成回复",

  // 斜杠命令
  "slash.compact": "压缩上下文",
  "slash.compactDesc": "立即压缩历史并写入摘要(可带强度与指令)",
  "slash.clear": "清空消息",
  "slash.clearDesc": "清空当前会话的全部消息",
  "slash.help": "帮助",
  "slash.helpDesc": "查看可用命令",
  "slash.helpBody": "可用命令:\n/compact [轻度|标准|重度] [压缩指令] - 立即压缩历史并写入摘要\n/clear 清空消息 - 清空当前会话的全部消息\n/help 帮助 - 查看可用命令",
  "slash.unknown": "未知命令:{cmd},输入 /help 查看可用命令",
  "slash.noSession": "没有活动会话,无法执行该命令",
  "slash.compactDoneSummary": "上下文已压缩并写入摘要:{before} → {after}",
  "slash.compactDonePruned": "上下文已整理:{before} → {after}",
  "slash.compactDoneUnchanged": "无需压缩:{before}(没有可折叠的旧轮次)",
  "slash.compactDoneEdited": "摘要已更新",
  "slash.compactFailed": "压缩失败:{reason}",
  "slash.compactBusy": "正在生成中,停止后再压缩",

  // 压缩卡片(历史中的摘要记录:查看/编辑/重生成/从压缩点建新会话)
  "compactCard.title": "上下文摘要 v{version}",
  "compactCard.digestTitle": "上下文整理记录",
  "compactCard.tokens": "{before} → {after}",
  "compactCard.viewFull": "查看全文",
  "compactCard.collapse": "收起",
  "compactCard.edit": "修正摘要",
  "compactCard.editPlaceholder": "写入更正后的摘要…",
  "compactCard.save": "保存",
  "compactCard.cancel": "取消",
  "compactCard.saved": "摘要已更新",
  "compactCard.saveFailed": "保存失败",
  "compactCard.regenerate": "重新生成",
  "compactCard.regenerated": "摘要已重新生成",
  "compactCard.forkFromPoint": "以压缩前内容新建会话",
  "compactCard.viewBackup": "查看压缩前完整记录",
  "compactCard.noBackup": "无备份(本次压缩未保留原文)",
  "compactCard.regenBusy": "正在生成中,稍后再试",

  // 压缩实时事件(随流展示,如工具执行过程)
  "trace.compaction": "上下文压缩 {before} → {after}",

  // 归档区(被折叠的原文,仅展示)
  "archive.title": "已压缩归档 {count} 条 · v{version}",
  "archive.stale": "备份已轮替,仅可查看",

  // 评价弹窗
  "rate.title": "您如何评价这个回应?",
  "rate.close": "关闭",
  "rate.scoreLow": "1 - 糟糕",
  "rate.scoreHigh": "10 - 很棒",
  "rate.why": "为什么?",
  "rate.reasons.style": "不喜欢这个文风",
  "rate.reasons.verbose": "过于冗长",
  "rate.reasons.unhelpful": "无帮助",
  "rate.reasons.incorrect": "事实并非如此",
  "rate.reasons.offTrack": "没有完全遵照指示",
  "rate.reasons.refused": "无理拒绝",
  "rate.reasons.lazy": "懒惰",
  "rate.reasons.other": "其他",
  "rate.detailsPlaceholder": "欢迎补充具体细节",
  "rate.tags.education": "教育",
  "rate.tags.tech": "科技",
  "rate.tags.college": "大学选择",
  "rate.tags.prompting": "提示词工程",
  "rate.addTag": "添加标签",
  "rate.addTagPlaceholder": "新标签…",
  "rate.removeTag": "移除标签",
  "rate.save": "保存",
} as const;

export type PrepMessageKey = keyof typeof prep;
