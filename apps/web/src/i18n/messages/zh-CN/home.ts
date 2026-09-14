/** home 文案(zh-CN 为 key 源;key 用点分路径,按 hero/features/steps/cta 区块前缀)。 */

export const home = {
  // Hero
  "hero.badge": "开源 · BYOK · 本地优先",
  "hero.title": "开源的 AI 模拟面试工具",
  "hero.desc":
    "面向个人开发者,在本地运行。上传简历,选择目标岗位,进行语音模拟面试,结束后生成评分与改进建议。自带 LLM API Key,无需注册账号。",
  "hero.cta.interview": "开始面试",
  "hero.cta.resume": "上传简历",

  // Hero 面试预览卡(演示内容)
  "hero.preview.status": "模拟面试进行中",
  "hero.preview.live": "Live",
  "hero.preview.interviewerInitial": "面",
  "hero.preview.interviewer": "面试官",
  "hero.preview.role": "后端工程师",
  "hero.preview.question":
    "请介绍一下你最近负责的项目,重点说明你做了什么决策,以及结果如何衡量。",
  "hero.preview.candidateInitial": "我",
  "hero.preview.you": "你",
  "hero.preview.answer":
    "上个季度我负责订单履约链路改造,把峰值延迟从 320ms 降到 110ms,QPS 提升 2.4 倍…",
  "hero.preview.videoStatus": "视频已连接",
  "hero.preview.micStatus": "语音识别中",

  // 功能区块
  "features.title": "主要功能",
  "features.desc": "覆盖面试准备、模拟面试到评分报告的完整流程。",
  "features.items.dynamic.title": "动态出题",
  "features.items.dynamic.desc": "根据简历和目标岗位生成问题,而非固定题库。",
  "features.items.probe.title": "深度追问",
  "features.items.probe.desc": "回答含糊时继续追问细节,直到讲清楚为止。",
  "features.items.company.title": "公司风格",
  "features.items.company.desc": "可按不同公司的面试风格调整提问方式与侧重。",
  "features.items.av.title": "音视频交互",
  "features.items.av.desc": "支持语音与摄像头实时对话。",
  "features.items.prep.title": "面试准备",
  "features.items.prep.desc": "上场前梳理要点,支持面经检索。",
  "features.items.report.title": "报告与成长",
  "features.items.report.desc": "每场面试生成评分与改进建议,可回看历史。",

  // 使用流程区块
  "steps.title": "使用流程",
  "steps.desc": "配置密钥、上传简历,即可开始一场模拟面试。",
  "steps.items.key.title": "接入密钥",
  "steps.items.key.desc": "在设置中配置自己的 LLM API Key,本地加密存储",
  "steps.items.resume.title": "上传简历",
  "steps.items.resume.desc": "解析简历内容,作为面试提问的依据",
  "steps.items.interview.title": "开始面试",
  "steps.items.interview.desc": "选择岗位与公司,进入语音模拟面试",
  "steps.go": "前往",

  // CTA 区块
  "cta.title": "配置完成后即可开始",
  "cta.desc": "无需注册账号,面试数据保存在本地。",
  "cta.action": "开始模拟面试",

  // 信任区块
  "trust.items.local.title": "本地优先",
  "trust.items.local.desc": "面试数据与密钥默认留在本机,不强制上云",
  "trust.items.byok.title": "自带密钥",
  "trust.items.byok.desc": "BYOK 接入你的 LLM,成本与模型自己掌控",
  "trust.items.opensource.title": "开源可审计",
  "trust.items.opensource.desc": "代码透明,流程可改,适合二次定制",
} as const;

export type HomeMessageKey = keyof typeof home;
