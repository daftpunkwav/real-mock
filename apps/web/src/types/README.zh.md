# types/

前端共享类型。

| 路径 | 用途 |
| --- | --- |
| `generated/` | OpenAPI 派生的 API 类型 — 由 `npm run generate:api-types` 再生成;禁止手工编辑 |
| `domains/` | 手工维护的按域前端类型(`api.ts` 处理器配置 / 语音目录 / 模型档案;`interview_ws.ts` WS 协议 — 由后端测试与 `protocol/interview_ws.schema.json` 锁定对齐;另有 `resume.ts`、`records.ts`、`report.ts`、`growth.ts`、`interview.ts`、`interview_prep.ts`) |
| `interview.ts` | `domains/interview.ts` 的兼容再导出 |
| `index.ts` | 桶式再导出 |
| `css.d.ts` / `process.d.ts` / `talkinghead.d.ts` | 环境模块声明 |
