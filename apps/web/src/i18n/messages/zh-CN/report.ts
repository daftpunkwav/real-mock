/** report 文案(面试报告域;key 用点分路径,zh-CN 为 key 源)。 */

export const report = {
  // 页面级(app/report/[id]/page.tsx + useReportLoad 加载失败回退)
  "page.loading": "生成报告中…",
  "page.retryCta": "生成 / 重新加载",
  "page.backToInterview": "返回面试",
  "errors.unavailable": "报告不可用",
  "errors.invalidSession": "无效的会话 ID",
  "errors.generateFailed": "报告生成失败，请重试",
  "errors.notGenerated": "报告尚未生成。可点击下方按钮生成或重新加载。",

  // 综合评分卡(ScoreSummaryCard)
  "summary.backLink": "返回记录",
  "summary.eyebrow": "Report",
  "summary.title": "面试评估报告",
  "summary.duration": "面试时长:{duration} 分钟",
  "summary.messagesCount": " · 有效对话 {count} 条",
  "summary.overallScore": "综合评分 / 100",

  // 短会话警告(ShortSessionAlert)
  "alerts.shortSession":
    "本场对话较短或有效作答很少,维度分可能偏低或接近 0,属评估结果而非页面缺数。",

  // 维度分(DimensionScores)
  "dimensions.technical": "技术能力",
  "dimensions.communication": "表达能力",
  "dimensions.projectDepth": "项目深度",
  "dimensions.problemSolving": "问题解决",
  "dimensions.presence": "临场状态",
  "dimensions.politeness": "话轮礼貌",

  // 能力雷达图(ScoreRadar)
  "radar.title": "能力雷达图",
  "radar.subtitle": "各轴满分 100;0 分会落在中心附近",
  "radar.technical": "技术",
  "radar.communication": "表达",
  "radar.projectDepth": "项目",
  "radar.problemSolving": "解题",
  "radar.presence": "临场",
  "radar.politeness": "礼貌",
  "radar.empty": "暂无有效维度分",

  // 分区标题(app/report/[id]/page.tsx → Section)
  "sections.strengths": "优势",
  "sections.weaknesses": "不足",
  "sections.resumeSuggestions": "简历改进建议",
  "sections.interviewSuggestions": "面试表现建议",
  "sections.improvementSuggestions": "综合建议",
  "sections.trainingPlan": "下一阶段训练计划",
  "sections.presenceMoments": "临场关键时刻",

  // 面试状态分析卡(FaceAnalysisCard)
  "face.title": "面试状态分析",

  // 页尾动作(ActionLinks)
  "actions.again": "再来一次",
  "actions.growth": "查看成长记录",

  // 会话回放(SessionLedgerReplay)
  "turns.replayTitle": "会话回放",
  "turns.ledgerFrozen": "ledger frozen",
  "turns.count": "{count} 轮",
  "turns.interviewer": "面试官",
  "turns.tools": "工具",
  "turns.candidate": "候选人",
  "turns.expand": "展开",
  "turns.collapse": "收起",
  "turns.toolOk": "ok",
  "turns.toolFail": "fail",
  "turns.toolArgs": "args",
  "turns.toolResult": "result",
  "turns.toolNameFallback": "tool",

  // 逐轮点评(TurnNotesSection)
  "turns.notesTitle": "逐轮点评",
  "turns.candidatePerformance": "候选人表现",
  "turns.interviewerReview": "面试官点评",
  "turns.intentLabel": "意图：",
  // 深度报告(ReAct 报告)
  "tabs.overview": "总览",
  "tabs.turns": "逐题解析",
  "tabs.verdict": "亮点与问题",
  "tabs.plan": "提升计划",
  "verdict.passed": "本轮判定：通过",
  "verdict.failed": "本轮判定：未通过",
  "sections.highlights": "亮点表现",
  "sections.keyProblems": "关键问题",
  "qa.intent": "考察意图",
  "qa.problems": "问题所在",
  "qa.reference": "参考答案",
  "qa.howToAnswer": "该如何回答",
  "qa.brushup": "知识巩固",
  "qa.exercises": "巩固练习",
  "qa.followup": "追问表现",
  "live.title": "报告生成中",
  "live.starting": "正在启动报告 agent…",
  "live.stageNotes": "逐题深读转写与简历证据",
  "live.stageSynthesis": "综合裁定评分与结论",
  "live.tool": "查证：{name}",
  "live.thinking": "思考中…",
  "live.working": "检索中…",

  "turns.qualityLabel": "质量：",
} as const;

export type ReportMessageKey = keyof typeof report;
