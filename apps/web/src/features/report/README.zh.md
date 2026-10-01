# features/report/

报告页领域:加载编排、标签页结构、逐题解析。

| 模块 | 用途 |
| --- | --- |
| `useReportLoad.ts` | 加载状态机:先快速路径 GET,生成中走实时 SSE,轮询兜底,A2003 收尾提交竞态重试,台账经 recordsHttp 兜底;`retryGenerate` 重启整条链路 |
| `reportTabs.ts` | 标签页 SSOT:id、i18n 标签键、按内容决定可见性(空标签不渲染);默认落在首个可见标签 |
| `turnGroups.ts` | 逐题笔记的纯分组:组内按台账轮次序,组间按阶段 SSOT 序(未知阶段按首次出现序,无阶段笔记殿后) |
| `liveEvents.ts` | 生成进度实时事件的 reducer(只保留最近 40 条) |
| `scoreFormat.ts` | 分数取整;缺失值渲染为破折号 |
| `components/` | 每个报告分区一张卡片;`TurnDeepNotes` 按阶段对逐题笔记分页(未激活组保持挂载、隐藏,以保留折叠状态) |

`app/report/[id]/page.tsx` 是唯一页面消费者:持有标签页选中态,只渲染激活面板。
