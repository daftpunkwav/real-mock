/** growth 文案(按 feature 迁移时填充;key 用点分路径,zh-CN 为 key 源)。 */

export const growth = {
  // 页面级(app/growth/page.tsx + useGrowthPage 加载失败回退)
  "page.eyebrow": "Growth",
  "page.title": "成长追踪",
  "page.loading": "加载中…",
  "page.loadFailed": "加载失败",

  // AI 成长洞察(InsightCard)
  "insight.title": "AI 成长洞察",
  "insight.refresh": "重新生成",
  "insight.generate": "生成成长分析",
  "insight.generating": "AI 正在分析你的面试历史…",
  "insight.loading": "加载中…",
  "insight.empty": "完成面试后,AI 会基于全部面试报告、简历与档案生成跨场成长分析。",
  "insight.stage.rising": "上升期",
  "insight.stage.stalling": "停滞",
  "insight.stage.plateau": "平台期",
  "insight.stage.insufficient": "样本不足",
  "insight.patterns": "反复出现的弱点",
  "insight.appearedIn": "出现 {count} 场",
  "insight.trend.worsening": "恶化",
  "insight.trend.stable": "持平",
  "insight.trend.improving": "好转",
  "insight.improving": "明显进步",
  "insight.gaps": "简历 vs 面试差距",
  "insight.plan": "下一阶段训练计划",
  "insight.basedOn": "基于最近 {count} 场面试报告",

  // 成长概览卡(GrowthSummaryCard + 本地档位词)
  "summary.level.none": "待启动",
  "summary.level.starting": "起步阶段",
  "summary.level.growing": "持续成长",
  "summary.level.advanced": "进阶提升",
  "summary.recordsIntro": "已积累 {count} 条成长记录",
  "summary.empty": "等待第一次面试",
  "summary.recordsLabel": "成长记录",
  "summary.plansLabel": "训练计划",
  "summary.weakSkillsLabel": "薄弱技能",
  "summary.lastTraining": "最近训练",
  "summary.records": "{count} 场",
  "summary.plans": "{count} 项",
  "summary.weakSkills": "{count} 个",
  "summary.focusTitle": "重点关注",
  "summary.planTitle": "当前计划",

  // 成长完成度卡(GrowthProgressCard)
  "progress.title": "成长完成度",
  "progress.hint": "多完成面试并执行训练计划,可提升完成度。",
  "progress.interviewCta": "模拟面试",
  "progress.prepCta": "面试准备",

  // 训练历史(TrainingHistorySection)
  "history.title": "训练历史",
  "history.session": "面试 #{id}",
  "history.report": "报告 →",
  "history.empty": "完成面试后将生成成长记录",
  "history.startCta": "开始模拟面试",

  // 高频薄弱项(TopWeaknessesSection)
  "weaknesses.title": "高频薄弱项",
  "weaknesses.occurrences": "出现 {count} 次",
  "weaknesses.empty": "完成模拟面试后将自动汇总薄弱技能",

  // 系统自我成长(SystemInsightsSection)
  "insights.title": "系统自我成长",
  "insights.description": "跨面试聚合:公司分布、工具调用、薄弱点沉淀。",
  "insights.toolsOn": " 工具循环已开启。",
  "insights.toolsOff": " 工具循环已关闭。",
  "insights.githubConfigured": " GitHub Token 已配置。",
  "insights.githubMissing": " 未配置 GITHUB_TOKEN。",
  "insights.sessionCount": "{count} 场",
  "insights.recentProbes": "近期线索",
  "insights.probeItem": "· [{company}] {point}",
} as const;

export type GrowthMessageKey = keyof typeof growth;
