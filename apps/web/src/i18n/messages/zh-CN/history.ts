/** history 文案(面试记录域;key 用点分路径,zh-CN 为 key 源)。 */

export const history = {
  // 页面头 + 列表(app/history/page.tsx + useHistoryPage + HistoryListCard)
  "list.eyebrow": "History",
  "list.title": "面试记录",
  "list.loading": "加载记录…",
  "list.loadFailed": "加载失败",
  "list.allSessions": "全部场次",
  "list.total": "{count} 场",
  "list.empty": "暂无面试记录",
  "list.startCta": "开始模拟面试",
  "list.ledgerBadge": "ledger",

  // 场次状态徽标(StatusBadge)
  "status.completed": "已完成",
  "status.active": "进行中",
  "status.pending": "待开始",

  // 数据概览统计格(HistoryDetailAside + StatCell)
  "stats.title": "数据概览",
  "stats.total": "总场次",
  "stats.completed": "已完成",
  "stats.active": "进行中",
  "stats.avgScore": "平均分",

  // 场次详情(HistoryDetailAside)
  "detail.title": "场次详情",
  "detail.role": "岗位",
  "detail.company": "公司",
  "detail.type": "类型",
  "detail.status": "状态",
  "detail.ledger": "Ledger",
  "detail.ledgerFrozen": "已冻结",
  "detail.ledgerUnfrozen": "未冻结",
  "detail.time": "时间",
  "detail.overallScore": "综合评分",
  "detail.currentPhase": "当前阶段",
  "detail.viewReport": "查看报告",
  "detail.continueInterview": "继续面试",
  "detail.notStarted": "该场次尚未开始",
  // 多轮面试(一面…五面)
  "list.round": "第{n}面",
  "result.passed": "通过",
  "result.failed": "未通过",
  "detail.roundResult": "轮次结果",
  "detail.nextRound": "进入第{n}面",
  "detail.nextRoundFailed": "进入下一轮失败",

  "detail.empty": "选择一条记录查看详情",
} as const;

export type HistoryMessageKey = keyof typeof history;
