# features/

feature 优先的业务模块。每个 feature 自持组件、hooks 与测试;跨 feature 的部分上移到 `src/components/` 与 `src/lib/`。

| Feature | 用途 |
| --- | --- |
| `home/` | 落地页 |
| `profile/` | 候选人档案编辑器 |
| `resume/` | 简历上传、评价、分页预览 |
| `settings/` | 设置页(供应商、模型、阶段、集成) |
| `prep/` | Prep 教练聊天 UI(输入区、上下文面板、slash 命令) |
| `interview/` | 面试房;房间的 hook 装配在 [interview/hooks/room/](interview/hooks/room/README.zh.md) 有独立 README |
| `report/` | 报告展示(标签页、分数格式化、实时事件) |
| `history/` | 面试历史页 |
| `growth/` | 成长统计页 |
| `media/` | 共享媒体原语:麦克风录音机([recorder/](media/recorder/README.zh.md))、TTS 播放器 |
| `avatar/` | 面试官数字人渲染(stage、portraits、scenes) |
