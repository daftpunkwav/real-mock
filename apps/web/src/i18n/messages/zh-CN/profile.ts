/**
 * @file profile.ts
 * @description profile 文案(zh-CN 为 key 源;en 同 key 集合)。
 */

export const profile = {
  // 页面骨架(PageHead / 页头按钮 / 加载态)
  "page.eyebrow": "Profile",
  "page.title": "个人档案",
  "page.loading": "加载档案…",
  "page.save": "保存档案",
  "page.clear": "清空信息",

  // 基本信息
  "basic.title": "基本信息",
  "basic.name.label": "姓名",
  "basic.gender.label": "性别",
  "basic.identity.label": "身份",
  "basic.email.label": "邮箱",
  "basic.phone.label": "电话 / 微信",

  // 教育背景
  "education.title": "教育背景",
  "education.school.label": "学校",
  "education.major.label": "专业",
  "education.level.label": "学历层次",
  "education.graduationYear.label": "毕业年份",
  "education.english.label": "英语水平",

  // 求职意向
  "jobIntent.title": "求职意向",
  "jobIntent.direction.label": "求职方向",
  "jobIntent.role.label": "目标岗位",
  "jobIntent.experience.label": "工作年限",
  "jobIntent.experienceDetail.label": "年限说明",
  "jobIntent.company.label": "当前公司",
  "jobIntent.salary.label": "期望薪资",
  "jobIntent.city.label": "所在城市",
  "jobIntent.expectedCity.label": "期望城市",
  "jobIntent.noticePeriod.label": "到岗时间",
  "jobIntent.remote.label": "远程意愿",

  // 技能与介绍
  "skills.title": "技能与介绍",
  "skills.selfIntro.label": "自我介绍",
  "skills.highlights.label": "职业亮点",
  "skills.projects.label": "代表项目",
  "skills.strengths.label": "优势",
  "skills.weaknesses.label": "待提升",
  "skills.certificates.label": "证书",
  "skills.domains.label": "技术领域",
  "skills.domains.add": "添加",
  "skills.domains.remove": "移除",
  "skills.domains.error": "请至少填写一项技术领域",

  // 在线身份
  "online.title": "在线身份",
  "online.github.label": "GitHub",
  "online.languages.label": "偏好语言",
  "online.portfolio.label": "作品集 / 博客",
  "online.linkedin.label": "LinkedIn",

  // 档案完整度
  "completion.title": "档案完整度",
  "completion.required": "必填",
  "completion.optional": "选填",
  "completion.missingList": "待补必填:{labels}",
  "completion.allReady": "所有必填项已就绪",

  // 档案预览
  "preview.unnamed": "未填写姓名",
  "preview.emptyHint": "完善档案以生成预览",
  "preview.major.label": "专业",
  "preview.major.value": "{major} · {year}",
  "preview.degree.label": "学历",
  "preview.role.label": "目标岗位",
  "preview.direction.label": "求职方向",
  "preview.company.label": "当前公司",
  "preview.expectedCity.label": "期望城市",
  "preview.city.label": "城市",
  "preview.email.label": "邮箱",
  "preview.phone.label": "电话/微信",
  "preview.github.label": "GitHub",
  "preview.domains.title": "技术栈",
  "preview.selfIntro.title": "自我介绍",

  // 未保存更改确认
  "unsaved.title": "未保存的更改",
  "unsaved.body": "离开当前页面后,未保存的修改将丢失。",
  "unsaved.stay": "留在此页",
  "unsaved.leave": "丢弃并离开",

  // 清空档案
  "clear.title": "清空档案",
  "clear.body": "将清除当前档案中的全部填写内容,此操作不可撤销。",
  "clear.cancel": "取消",
  "clear.confirm": "确认清空",
  "clear.success": "已清空",
  "clear.failed": "清空失败",

  // 保存 / 加载状态提示
  "save.missingRequired": "请先填写必填项:{labels}",
  "save.success": "已保存",
  "save.failed": "保存失败",
  "load.failed": "加载失败",

  // 表单通用错误
  "field.requiredError": "请填写{label}",

  // 列表连接符(必填缺失项串接)
  "format.listSeparator": "、",
} as const;

export type ProfileMessageKey = keyof typeof profile;
