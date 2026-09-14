/** 侧栏导航文案(label 由 config/nav.ts 的 labelKey 指向这里)。 */

export const nav = {
  "aria.main": "主导航",
  "items.home": "首页",
  "items.profile": "个人档案",
  "items.resume": "简历管理",
  "items.prep": "面试准备",
  "items.interview": "模拟面试",
  "items.history": "面试记录",
  "items.growth": "成长追踪",
  "items.settings": "设置",
} as const;

export type NavMessageKey = keyof typeof nav;
