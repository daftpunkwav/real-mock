# config/

静态前端配置。文件只持键与 id — 用户可见文案在 i18n catalog 中。

| 文件 | 用途 |
| --- | --- |
| `nav.ts` | 导航项 |
| `pageLayout.ts` | 每页布局元数据 |
| `phases.ts` | 面试阶段 id / 标签;镜像后端 SSOT(`realmock.domains.interview.workflows`),由 `apps/api/tests/interview/test_phase_ssot.py` 守护 |
| `prepPrompts.ts` | Prep 快捷提示键(文案在 `i18n/messages/<locale>/prep.ts`) |
