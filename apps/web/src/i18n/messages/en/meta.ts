/** Document metadata: content that follows the locale (document.title etc.). */

export const meta = {
  "app.title": "RealMock — AI Mock Interview",
  "app.description": "Agent-based realistic mock interview system with BYOK",
} as const;

export type MetaMessageKey = keyof typeof meta;
