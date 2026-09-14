/** Common strings: actions, states, shell control labels (theme/locale toggles). */

export const common = {
  "action.confirm": "Confirm",
  "action.cancel": "Cancel",
  "action.retry": "Retry",
  "action.copy": "Copy",
  "action.close": "Close",
  "action.save": "Save",
  "action.delete": "Delete",
  "action.edit": "Edit",
  "action.test": "Test",
  "state.loading": "Loading…",
  "state.saving": "Saving…",
  "state.empty": "Nothing here yet",
  "state.error": "Something went wrong",
  "request.failed": "Request failed: {status}",
  "stream.failed": "Streaming output failed",
  "theme.light": "Light",
  "theme.dark": "Dark",
  "theme.system": "System",
  "theme.toggle.title": "Theme: {label} (click to switch)",
  "theme.toggle.aria": "Current theme {label}, click to switch",
  "locale.toggle.title": "UI language: {label} (click to switch)",
  "locale.toggle.aria": "Current UI language {label}, click to switch",

  // Shared component layer (Toast/ConfirmDialog/LoadError/ModelSelect/ContextGauge/Sidebar/boundary pages)

  // Extra actions (Back to home shared by error and not-found; Toast close reuses action.close)
  "action.backHome": "Back to home",

  // ConfirmDialog default buttons
  "confirm.confirm": "Confirm",
  "confirm.cancel": "Cancel",

  // LoadError
  "load.failed": "Load failed",
  "load.hint.notConfigured": "(not configured)",
  "load.hint.checkEnv": "Please check the NEXT_PUBLIC_* environment variables",
  "load.backendHintPrefix": "Make sure the backend is running (current config: ",
  "load.backendHintSuffix": "). If you just changed the port, restart the frontend.",

  // ModelSelect / EffortSelect
  "model.effort.low": "Low",
  "model.effort.medium": "Medium",
  "model.effort.high": "High",
  "model.effort.max": "Max",
  "model.effort.aria": "Reasoning effort",
  "model.notSet": "Not set",
  "model.useDefault": "Default ({label})",

  // ContextGauge
  "context.usage": "Context usage {percent}",
  "context.usageAria": "Context usage",
  "context.panel.title": "Context capacity",
  "context.panel.usage": "{used}/{total} ({percent})",
  "context.panel.usageNoModel": "{used} (no model selected)",
  "context.noMessages": "No messages yet",
  "context.promptTokens": "Input tokens",
  "context.completionTokens": "Output tokens",
  "context.cacheRate": "Cache hit rate",
  "context.cacheRateValue": "{percent} ({tokens})",
  "context.estimated": "est.",
  "context.estimatedHint": "Provider reported no input usage; mechanically estimated from context, indicative only",
  "context.bucket.user": "Messages",
  "context.bucket.userHint": "Message bodies you sent",
  "context.bucket.assistant": "Replies",
  "context.bucket.assistantHint": "Final reply text, excluding reasoning and tools",
  "context.bucket.thinking": "Reasoning",
  "context.bucket.thinkingHint": "Model thinking, billed as output",
  "context.bucket.tools": "Tools & retrieval",
  "context.bucket.toolsHint": "Tool calls, search results, and execution records",
  "context.bucket.system": "System prompt",
  "context.bucket.systemHint": "Coach persona, resume/company context, language rules",
  "context.bucket.memory": "Memory & summaries",
  "context.bucket.memoryHint": "Long-term memory index, compaction summaries, referenced sessions",
  "context.bucket.other": "Other",
  "context.bucket.otherHint": "Unclassified context content",

  // Sidebar
  "sidebar.openNav": "Open navigation",
  "sidebar.closeNav": "Close navigation",
  "sidebar.expand": "Expand sidebar",
  "sidebar.collapse": "Collapse sidebar",
  "sidebar.resize": "Drag to resize sidebar",

  // not-found page
  "nf.title": "Page not found",
  "nf.description": "This link may have been deleted, merged, or never existed.",

  // error boundary page
  "err.eyebrow": "Error",
  "err.title": "Something went wrong",
  "err.unknown": "Unknown error, please try again later.",
  "err.trace": "trace: {digest}",

  // Code blocks
  "code.plain": "plain text",
  "code.copy": "Copy",
  "code.copied": "Copied",
  "code.run": "Run",
  "code.stop": "Stop",
  "code.running": "Running…",
  "code.output": "Output",
  "code.status.ok": "Done",
  "code.status.error": "Error",
  "code.status.timeout": "Timeout",
  "code.status.cancelled": "Cancelled",
  "code.status.unavailable": "Unavailable",
  "code.durationMs": "{ms} ms",
  "code.truncated": "Output truncated",
  "code.closeOutput": "Close output",
  "code.diagram": "Diagram",
  "code.source": "Source",
  "code.zoomIn": "Zoom in",
  "code.zoomOut": "Zoom out",
  "code.zoomReset": "Reset to 100%",
  "code.fullscreen": "View fullscreen",
  "code.diagramFailed": "Diagram failed to render; showing source",
  "code.errorDetail": "Technical details",
} as const;

export type CommonMessageKey = keyof typeof common;
