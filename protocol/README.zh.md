# protocol/

后端与前端共享的线上协议 schema。

| 文件 | 用途 |
| --- | --- |
| `interview_ws.schema.json` | 面试 WebSocket 事件词汇表 SSOT(服务端 / 客户端事件类型与载荷)。与后端 `realmock.domains.interview.constants`、前端 `apps/web/src/types/domains/interview_ws.ts` 保持对齐;后端测试 `tests/interview/test_ws_protocol_schema.py` 守护该对齐 |
