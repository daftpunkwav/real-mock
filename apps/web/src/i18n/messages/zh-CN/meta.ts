/** 文档元数据:document.title 等随 locale 更新的内容。 */

export const meta = {
  "app.title": "RealMock — AI 智能模拟面试",
  "app.description": "基于 AI Agent 的真实面试模拟系统,支持 BYOK",
} as const;

export type MetaMessageKey = keyof typeof meta;
