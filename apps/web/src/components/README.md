# components/

Cross-feature presentational components. Feature-specific UI stays in `features/`.

| Group | Contents |
| --- | --- |
| Markdown rendering | `MarkdownContent.tsx`, `markdownComponents.tsx`, `CodeBlock.tsx`, `SyntaxHighlight.tsx` (+ module CSS), `MermaidBlock.tsx`, `markdownSafeUrl.ts` |
| Primitives | `Select.tsx`, `Toast.tsx`, `ConfirmDialog.tsx`, `Spinner.tsx`, `CollapsibleSection.tsx`, `LoadError.tsx`, `ContextGauge.tsx`, `ModelSelect.tsx`, `ModelControls.tsx`, `StreamingReveal.tsx` |
| `layout/` | App shell: `AppShell.tsx`, `Sidebar.tsx`, `SidebarNav.tsx`, `sidebarStorage.ts` |
| `theme/` | `ThemeProvider.tsx`, `ThemeToggle.tsx` |
| `brand/` | `LogoMark.tsx` |
| Other | `diagramSvg.ts` (diagram SVG helpers), `useDialogScrollLock.ts` (shared dialog scroll-lock hook) |
