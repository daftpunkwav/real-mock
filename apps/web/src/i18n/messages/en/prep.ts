/**
 * @file prep.ts
 * @description prep messages (en; key set must mirror zh-CN exactly).
 */

export const prep = {
  // Page header
  "page.eyebrow": "Prep Coach",
  "page.title": "Interview Prep",

  // Chat area (page-level buttons / error lines / thinking process)
  "chat.dismissError": "Dismiss error",
  "chat.jumpToBottom": "Back to bottom",
  "chat.sendFailedFallback": "failed",
  "chat.replyInterrupted": "Reply interrupted: {reason}",
  "chat.replyError": "Error: {reason}",

  // Composer
  "composer.placeholder": "Ask me anything about interviews…",
  "composer.placeholderQueued": "Generating; your input will be queued…",
  "composer.compacting": "Compacting context; please wait…",
  "composer.multilineHint": "Enter to send, Shift+Enter for a new line",
  "composer.selectModel": "Select model",
  "composer.send": "Send",
  "composer.refChips": "Sessions referenced this turn",
  "composer.refRemove": "Remove reference",
  "composer.refMenuTitle": "Reference sessions (this turn only)",
  "composer.refMenuEmpty": "No sessions to reference",

  // Token usage breakdown
  "tokens.gauge.messages": "Messages",
  "tokens.gauge.replies": "Replies",
  "tokens.gauge.system": "System & tools",

  // Empty state (before coaching starts)
  "empty.title": "Start your interview coaching",
  "empty.desc": "After linking a resume, the AI coach will tailor guidance to your background.",
  "empty.resumeLabel": "Linked resume",
  "empty.resumeActiveSuffix": " (applied)",
  "empty.noResume": "No resume yet — upload one in \"Resume Management\" first, or start with general coaching",
  "empty.starting": "Connecting…",
  "empty.start": "Start coaching",

  // Session list
  "sessions.title": "Chat history",
  "sessions.new": "New chat",
  "sessions.empty": "No conversations yet; one is saved automatically after your first message",
  "sessions.genericGroup": "General coaching",
  "sessions.newSessionFallback": "New session",
  "sessions.messageCount": "{count} messages",
  "sessions.time.justNow": "just now",
  "sessions.time.minutesAgo": "{n} min ago",
  "sessions.time.hoursAgo": "{n} hr ago",
  "sessions.time.daysAgo": "{n} d ago",

  // Session lifecycle
  "sessions.welcome":
    "Hi! I'm your interview prep coach. Tell me your target role, or let me analyze your resume and create practice questions.",
  "sessions.switchFailed": "Failed to switch session: {reason}",
  "sessions.switchFailedFallback": "Failed to switch session",
  "sessions.createFailed": "Failed to create coaching session",
  "sessions.backendDown": "Backend is not responding; confirm it is running",
  "sessions.backendUnstable": "Backend connection is unstable, retry failed; try again later",
  "sessions.delete": "Delete",
  "sessions.generating": "Generating; use the stop button to stop this session",
  "sessions.stopGeneration": "Stop generation",
  "sessions.deleteTitle": "Delete session",
  "sessions.deleteBody": "Delete this session and all its messages? This cannot be undone.",
  "sessions.deleteFailed": "Failed to delete session",
  "sessions.archive": "Archive",
  "sessions.archiveTitle": "Archive session",
  "sessions.archiveBody": "Archived sessions move to the archive group but stay usable.",
  "sessions.archiveFailed": "Archive operation failed",
  "sessions.unarchive": "Unarchive",
  "sessions.unarchiveTitle": "Unarchive session",
  "sessions.unarchiveBody": "Move this session back to the list?",
  "sessions.clear": "Clear messages",
  "sessions.clearTitle": "Clear session messages",
  "sessions.clearBody": "Clear all messages in this session? This cannot be undone.",
  "sessions.clearFailed": "Failed to clear messages",
  "sessions.cancelAction": "Cancel",
  "sessions.archivedTitle": "Archived · {count}",

  // Search cards / resume loading
  "resources.sourcesSummary": "Sources · {total} results / {groups} groups",
  "resources.queryLabel": "Query: {query}",
  "resources.resumeLoadFailed": "Failed to load resume list",

  // Side panel
  "panel.resumeTitle": "Linked resume",
  "panel.resumeActive": "Current application",
  "panel.resumeInactive": "Not set as application",
  "panel.resumeScore": " · Score {score}",
  "panel.noResume": "No resume linked; general coaching will be used",
  "panel.quickPrompts": "Quick prompts",

  // Quick prompts (full sentences written into the composer on click)
  "quick.analyzeResume": "Help me analyze the strengths and gaps in my resume",
  "quick.techQuestions": "Give me 5 technical interview questions for my target role",
  "quick.behavioralMock": "Run a behavioral interview mock and critique my answers",
  "quick.searchExperiences": "Search recent interview experiences and summarize common topics",

  // Agent tool names
  "agent.tool.webSearch": "Search interview experiences",
  "agent.tool.companyInfo": "Look up company",
  "agent.tool.quiz": "Create practice questions",
  "agent.tool.askUser": "Ask you a question",
  "agent.tool.takeNote": "Take notes",
  "agent.tool.memoryListTags": "List memory tags",
  "agent.tool.memoryListSummaries": "List memory summaries",
  "agent.tool.memoryGetDetail": "Read memory detail",
  "agent.tool.memoryWrite": "Write long-term memory",
  "agent.tool.githubListRepos": "View GitHub repos",
  "agent.tool.githubGetReadme": "Read repo README",
  "agent.tool.githubGetRepo": "View repo details",
  "agent.tool.githubGetFile": "Read repo file",
  "agent.tool.githubListCommits": "View commits",
  "agent.tool.githubGetUser": "View GitHub user",
  "agent.tool.compactContext": "Compact context",
  "agent.tool.searchTools": "Search tools",
  "agent.tool.codeExec": "Run code",

  // Agent question modal
  "ask.title": "Coach wants to confirm",
  "ask.customPlaceholder": "Or type a custom answer…",
  "ask.send": "Send answer",
  "ask.dismiss": "Not now — reply in the input box later",
  "ask.confirm": "Confirm",
  "ask.progress": "Answered {answered}/{total}",
  "ask.multiHint": "Multiple choices allowed",
  "ask.recommended": "Recommended",
  "ask.autoIn": "Auto-selecting “{choice}” in {time}",

  // Thinking/execution timeline
  "trace.title": "Thinking & actions",
  "trace.rawName": "Raw name:",
  "trace.detailArgs": "Arguments",
  "trace.detailResult": "Result",

  // Message actions
  "actions.copy": "Copy",
  "actions.copyFailed": "Copy failed",
  "actions.export": "Export as Markdown",
  "actions.fork": "Fork a new session from here",
  "actions.forkFailed": "Fork failed",
  "actions.regenerate": "Regenerate",
  "actions.regenerateFailed": "No question found to regenerate",
  "actions.regenerateLatestOnly": "Only the latest reply can be regenerated",
  "actions.rate": "Rate this response",
  "actions.rateDone": "Rating saved as a long-term memory",
  "actions.rateFailed": "Failed to save rating",
  "actions.retract": "Retract this message and everything after",
  "actions.retractFailed": "Retract failed",

  // Stop and stopped state
  "composer.stop": "Stop generating",
  "chat.stopped": "Stopped",
  "chat.stoppedEmpty": "Stopped before any reply was generated",

  // Slash commands
  "slash.compact": "Compact context",
  "slash.compactDesc": "Compact history and write a summary now (intensity + directive supported)",
  "slash.clear": "Clear messages",
  "slash.clearDesc": "Clear all messages in the current session",
  "slash.help": "Help",
  "slash.helpDesc": "List available commands",
  "slash.helpBody": "Available commands:\n/compact [light|balanced|aggressive] [directive] - compact history and write a summary now\n/clear Clear messages - clear all messages in the current session\n/help Help - list available commands",
  "slash.noSession": "No active session; cannot run that command",
  "slash.compactDoneSummary": "Context compacted with summary: {before} → {after}",
  "slash.compactDonePruned": "Context tidied: {before} → {after}",
  "slash.compactDoneUnchanged": "Nothing to compact: {before} (no older turns to fold)",
  "slash.compactFailed": "Compaction failed: {reason}",
  "slash.compactBusy": "Generation in progress; stop it before compacting",

  // Compaction card (persisted summary record: view/edit/regenerate/fork-from-point)
  "compactCard.title": "Context summary v{version}",
  "compactCard.digestTitle": "Context tidy-up record",
  "compactCard.tokens": "{before} → {after}",
  "compactCard.edit": "Correct summary",
  "compactCard.editPlaceholder": "Write the corrected summary…",
  "compactCard.save": "Save",
  "compactCard.cancel": "Cancel",
  "compactCard.saved": "Summary updated",
  "compactCard.saveFailed": "Save failed",
  "compactCard.regenerate": "Regenerate",
  "compactCard.forkFromPoint": "New session from pre-compaction content",
  "compactCard.viewBackup": "View pre-compaction record",

  // Live compaction event (streamed like tool execution)
  "trace.compaction": "Context compacted {before} → {after}",

  // Archive section (folded originals, display-only)
  "archive.title": "{count} archived messages · v{version}",
  "archive.stale": "backup rotated, view-only",

  // Rating modal
  "rate.title": "How would you rate this response?",
  "rate.close": "Close",
  "rate.scoreLow": "1 - Poor",
  "rate.scoreHigh": "10 - Great",
  "rate.why": "Why?",
  "rate.reasons.style": "Dislike the writing style",
  "rate.reasons.verbose": "Too verbose",
  "rate.reasons.unhelpful": "Not helpful",
  "rate.reasons.incorrect": "Factually wrong",
  "rate.reasons.offTrack": "Did not follow instructions",
  "rate.reasons.refused": "Unjustified refusal",
  "rate.reasons.lazy": "Lazy",
  "rate.reasons.other": "Other",
  "rate.detailsPlaceholder": "Add more details (optional)",
  "rate.tags.education": "Education",
  "rate.tags.tech": "Tech",
  "rate.tags.college": "College choice",
  "rate.tags.prompting": "Prompt engineering",
  "rate.addTag": "Add tag",
  "rate.addTagPlaceholder": "New tag…",
  "rate.removeTag": "Remove tag",
  "rate.save": "Save",
} as const;

export type PrepMessageKey = keyof typeof prep;
