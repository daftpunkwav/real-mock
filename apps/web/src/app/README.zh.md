# app/

Next.js App Router:每个页面一个路由段。

| 路由段 | 页面 |
| --- | --- |
| `page.tsx` | 首页 |
| `profile/` | 候选人档案编辑器 |
| `resume/` | 简历列表 / 上传 / 评价;`resume/preview/` 为服务端渲染的预览页 |
| `settings/` | 设置 |
| `prep/` | Prep 教练会话 |
| `interview/[id]/` | 面试房 |
| `report/[id]/` | 报告查看 |
| `history/` | 面试历史 |
| `growth/` | 成长统计 |
| `avatar-debug/` | 数字人调试页 |

外壳文件:`layout.tsx`(根布局)、`error.tsx`、`loading.tsx`、`not-found.tsx`、`globals.css`。
