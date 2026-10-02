# features/prep/

Prep 教练聊天:会话、流式发送管线、单条消息操作。

## 入口与装配

`usePrepChat` 是装配根,也是唯一导出的 hook(`index.ts`;纯工具 —— history
归一化、上下文估算、slash 命令、"#" 会话引用 —— 与流注册表一并导出)。它组装:

| 部分                                         | 职责                                                                |
| -------------------------------------------- | ------------------------------------------------------------------- |
| `hooks/usePrepResources`                     | 简历、会话、模型档案                                                |
| `hooks/usePrepChatSession`                   | 恢复 / 切换 / 新建,历史消息播种,用量合计                            |
| `hooks/usePrepSend`                          | 发送管线:按会话排队、流式处理器、中止/停止、用量合并、后端索引登记  |
| `hooks/usePrepMessageActions`                | 导出 / fork / 重新生成 / 撤回 / 评分                                |
| `hooks/usePrepCompact`                       | 手动 `/compact`、摘要编辑、折叠轮次的本地存档                       |
| `hooks/usePrepSessionManage`                 | 删除 / 归档 / 恢复 / 清空(先停在途流)                               |
| `hooks/usePrepScroll`、`hooks/useTokenBatch` | 自动跟随滚动、rAF token 批处理                                      |
| `streamRegistry.ts`                          | 模块级在途流注册表,按会话 id 键控 —— 切换会话与应用内导航都不会中断 |

## 不变量

- `backendIndex` 登记(每条新轮次预留 user + assistant 两条)支撑 fork /
  撤回 / 重新生成;漂移由服务端真值修复(done 信封、消息列表重同步)。
  重新生成替换末尾的 user+assistant 消息对。
- 手动压缩进行中拒绝发送;折叠轮次经 `compactionArchive.ts` 保持可见
  (仅展示用,localStorage,按会话隔离)。
- "#" 会话引用只附着于单轮,不持久化为链接。
- AI 快捷提问在当前会话每轮落定后刷新;刷新为空或失败时保留当前卡片。
