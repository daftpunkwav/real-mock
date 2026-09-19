# components/

跨 feature 的展示组件。feature 专属 UI 留在 `features/`。

| 分组 | 内容 |
| --- | --- |
| Markdown 渲染 | `MarkdownContent.tsx`、`markdownComponents.tsx`、`CodeBlock.tsx`、`SyntaxHighlight.tsx`(含 module CSS)、`MermaidBlock.tsx`、`markdownSafeUrl.ts` |
| 基础控件 | `Select.tsx`、`Toast.tsx`、`ConfirmDialog.tsx`、`Spinner.tsx`、`CollapsibleSection.tsx`、`LoadError.tsx`、`ContextGauge.tsx`、`ModelSelect.tsx`、`ModelControls.tsx`、`StreamingReveal.tsx` |
| `layout/` | 应用外壳:`AppShell.tsx`、`Sidebar.tsx`、`SidebarNav.tsx`、`sidebarStorage.ts` |
| `theme/` | `ThemeProvider.tsx`、`ThemeToggle.tsx` |
| `brand/` | `LogoMark.tsx` |
| 其他 | `diagramSvg.ts`(图形 SVG 助手)、`useDialogScrollLock.ts`(共享的弹窗滚动锁 hook) |
