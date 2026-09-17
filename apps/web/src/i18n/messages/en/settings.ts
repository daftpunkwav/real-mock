/** Settings page (interface preferences + BYOK providers/models). */

export const settings = {
  "page.title": "Settings",
  "page.loading": "Loading…",
  "nav.interface": "Interface",
  "nav.models": "Models & Processors",
  "nav.resume": "Resumes",
  "nav.prep": "Interview Prep",
  "nav.interview": "Mock Interview",
  "nav.integrations": "Integrations",

  // InterviewSettingsPanel
  "interviewPanel.title": "Question-style brief cache",
  "interviewPanel.desc":
    "When configuring a mock interview, AI researches the target company's question style, focus areas, and interview flow online, cached per company. Clearing it forces fresh research on the next configuration.",
  "interviewPanel.clear": "Clear brief cache",
  "interviewPanel.clearConfirmTitle": "Clear question-style brief cache",
  "interviewPanel.clearConfirmMessage":
    "This deletes all cached company briefs. The next mock-interview setup will research online again, so the first load will be slower.",
  "interviewPanel.cleared": "Cleared {count} cached briefs",
  "interviewPanel.clearFailed": "Failed to clear",
  "theme.title": "Theme",
  "provider.pickHint": "Select or add a provider on the left",
  "language.title": "UI language",
  "language.hint":
    "Affects the interface language only; it does not change the language the interviewer speaks.",

  // ProviderList ("+" toggles the add panel)
  "providerList.title": "Providers",
  "providerList.empty": "No providers yet — use + above to add one",
  "providerList.namePlaceholder": "Name, e.g. DeepSeek",
  "providerList.add": "Add provider",
  "providerList.createCustom": "Create",
  "providerList.createFailed": "Failed to create",

  // AddProviderPanel: one-click adapted vendors
  "recommended.title": "Adapted vendors",
  "recommended.empty": "No recommended vendors yet",
  "recommended.loadFailed": "Failed to load recommended vendors",
  "recommended.hint":
    "Click a vendor to auto-configure the reasoning / STT / TTS channels (Base URL + names, one default entry each); API Keys stay blank — fill them in each tab on the right. Or create a custom provider with a name below.",
  "recommended.applyHint": "Configure all three model channels in one click",
  "recommended.applied": "Provider {provider} configured; fill the API Keys in each tab",
  "recommended.adding": "Configuring…",
  "recommended.addFailed": "Failed to configure",
  "recommended.close": "Collapse the add panel",

  // ChannelCard
  "channelCard.save": "Save this type",
  "channelCard.saving": "Saving…",
  "channelCard.saved": "Channel saved",
  "channelCard.saveFailed": "Failed to save",

  // Kind tabs
  "kinds.chat": "Reasoning LLM",
  "kinds.stt": "Speech-to-text",
  "kinds.tts": "Text-to-speech",

  // Model catalog fetch
  "catalog.fetch": "Fetch model list",
  "catalog.loading": "Fetching…",
  "catalog.pickAria": "Pick a model from the list",
  "catalog.loadFailed": "Failed to fetch the model list",

  // ProviderCard
  "providerCard.name.label": "Name",
  "providerCard.baseUrl.label": "Base URL",
  "providerCard.fullUrl.label": "Full URL",
  "providerCard.fullUrl.hint":
    "When on, enter the complete request URL (no trailing slash) for nonstandard endpoints such as voice APIs; when off, paths are appended per API format",
  "providerCard.apiFormat.label": "API format",
  "providerCard.apiFormat.disabledHint": "API format is ignored in full-URL mode",
  "providerCard.apiKey.label": "API Key",
  "providerCard.apiKey.setHint": " (set; leave blank to keep)",
  "providerCard.show": "Show",
  "providerCard.hide": "Hide",
  "providerCard.enabled": "Enabled",
  "providerCard.website.label": "Website",
  "providerCard.website.placeholder": "https://…",
  "providerCard.notes.label": "Notes",
  "providerCard.delete": "Delete",
  "providerCard.deleteConfirmTitle": "Delete provider",
  "providerCard.deleteConfirmMessage":
    "This permanently deletes \"{name}\" together with all its model entries, channel settings, and task bindings pointing at them.",
  "providerCard.saving": "Saving…",
  "providerCard.save": "Save provider",
  "providerCard.saved": "Provider saved",
  "providerCard.saveFailed": "Failed to save",
  "providerCard.deleted": "Provider deleted",
  "providerCard.deleteFailed": "Failed to delete",

  // ModelListCard
  "modelList.count": "Model entries ({count})",
  "modelList.add": "Add model",
  "modelList.edit": "Edit model",
  "modelList.empty":
    "No model entries yet; entries declare capabilities and can serve multiple tasks",
  "modelList.emptyKind": "No entries for this model type yet — use \"Add model\" to create one",

  // ModelRow
  "modelRow.test": "Test",
  "modelRow.edit": "Edit",
  "modelRow.delete": "Delete",

  // CAP_OPTIONS
  "caps.chat": "Chat / Reasoning",
  "caps.vision": "Vision input",
  "caps.audio_input": "Audio input",
  "caps.audio_output": "Audio output",
  "caps.reasoning": "Reasoning effort",

  // ModelForm
  "modelForm.model.label": "Model name (sent to API)",
  "modelForm.model.placeholder": "e.g. deepseek-chat",
  "modelForm.displayName.label": "Display name (optional)",
  "modelForm.contextWindow.label": "Context window (tokens)",
  "modelForm.maxOutput.label": "Max output (tokens)",
  "modelForm.capabilities.label":
    "Capabilities (multi-select; one model can serve multiple tasks)",
  "modelForm.extras.summary": "Advanced params (JSON, e.g. voice credentials)",
  "modelForm.cancel": "Cancel",
  "modelForm.saving": "Saving…",
  "modelForm.save": "Save model",

  // TASK_META
  "tasks.chat.label": "Reasoning (chat)",
  "tasks.chat.hint": "Default model for interview coach, mock interviews and resume feedback",
  "tasks.stt.label": "Speech input (stt)",
  "tasks.stt.hint": "Interview speech recognition; falls back per the degradation policy on failure",
  "tasks.tts.label": "Speech output (tts)",
  "tasks.tts.hint": "Interviewer playback; falls back per the degradation policy on failure",

  // BindingsCard
  "bindings.title": "Default processors",
  "bindings.desc":
    "Default entries used when a task has no manually picked model; the degradation policy for voice tasks applies when they fail.",
  "bindings.selectAria": "Default model for {task}",
  "bindings.unset": "Not set",
  "bindings.noModels": "No models available",
  "bindings.optionLabel": "{label} ({provider})",

  // useSettingsPage
  "toast.loadFailed": "Failed to load",
  "toast.extrasInvalidJson": "Advanced params are not valid JSON",
  "toast.modelNameRequired": "Model name is required",
  "toast.modelUpdated": "Model updated",
  "toast.modelAdded": "Model added",
  "toast.saveFailed": "Failed to save",
  "toast.deleted": "Deleted",
  "toast.deleteFailed": "Failed to delete",
  "toast.testPassed": "Test passed",
  "toast.testNotPassed": "Test did not pass",
  "toast.testFailed": "Test failed",
  "toast.bindingUpdated": "Default processor updated",
  // DataSettingsPanel
  "data.clearResults.title": "Clear deep-review history",
  "data.clearResults.desc":
    "Erase AI deep-review results and scores for every resume; resume files stay. This cannot be undone.",
  "data.clearResults.action": "Clear review history",
  "data.clearResults.confirmTitle": "Clear review history",
  "data.clearResults.confirmBody":
    "Clear deep-review results for all resumes? Files stay, and this cannot be undone.",
  "data.clearResults.done": "Cleared review results for {count} resumes",
  "data.clearResults.failed": "Failed to clear",
  "data.clearAll.title": "Delete all resumes",
  "data.clearAll.desc":
    "Delete every resume file and version; their review history goes with them. This cannot be undone.",
  "data.clearAll.action": "Delete all resumes",
  "data.clearAll.confirmTitle": "Delete all resumes",
  "data.clearAll.confirmBody":
    "Delete every resume? Files and review history will be gone, and this cannot be undone.",
  "data.clearAll.done": "Deleted {count} resumes",
  "data.clearAll.failed": "Failed to delete",

  // Prep long-term memories (only agent-recorded memories can be edited, never created)
  "memories.title": "Prep long-term memories",
  "memories.desc":
    "Long-term memories distilled from user ratings and agent notes, injected into every turn. Existing memories can only be edited or deleted, never created by hand.",
  "memories.searchPlaceholder": "Search summaries…",
  "memories.tagFilter": "Filter by tag",
  "memories.tagAll": "All tags",
  "memories.reload": "Reload",
  "memories.empty": "No memories yet. Rate a response in chat, or let the agent record key points.",
  "memories.selectAll": "Select all",
  "memories.selected": "{count} selected",
  "memories.batchDelete": "Delete selected",
  "memories.confirmTitle": "Delete memories",
  "memories.confirmBody": "Delete the selected {count} memories? This cannot be undone.",
  "memories.cancel": "Cancel",
  "memories.edit": "Edit",
  "memories.editTitle": "Edit memory",
  "memories.summary": "Summary",
  "memories.agentMaintained": "Maintained by the agent",
  "memories.tagsTitle": "Tags",
  "memories.comment": "Comment",
  "memories.score": "Score (1–10, blank clears)",
  "memories.save": "Save",
  "memories.saved": "Saved",
  "memories.saveFailed": "Save failed",
  "memories.batchDeleted": "Deleted {count} memories",
  "memories.deleteFailed": "Delete failed",
  "memories.loadFailed": "Failed to load memories",
  "memories.detailUserInput": "User input",
  "memories.detailAgentOutput": "Agent output",
  "memories.detailComment": "Comment",
  "memories.detailReasons": "Reasons",
  "memories.detailLoading": "Loading detail…",
  "memories.expand": "Expand detail",
  "memories.collapse": "Collapse detail",
  "memories.origin.user_rating": "User rating",
  "memories.origin.user_emphasis": "User emphasis",
  "memories.origin.agent_note": "Agent note",

  // Auto-compact: the agent summarizes history with the LLM once context usage hits the threshold
  "prep.compact.title": "Auto-compact",
  "prep.compact.desc":
    "At the start of every turn, history compacts once context usage reaches the selected share; the auto mode lets the agent decide and invoke the compaction tool itself, streamed like any other tool. Compaction always summarizes with the LLM — never a silent truncation. Manual /compact takes parameters (intensity + directive) and ignores the trigger share. The retain count constrains auto compaction only: old tool results always fold, and a manual /compact may fold past it straight to the latest turn.",
  "prep.compact.label": "Context usage that triggers compaction",
  "prep.compact.auto": "Auto (agent decides)",
  "prep.compact.percent": "{n}%",
  "prep.compact.intensityLabel": "Compression intensity",
  "prep.compact.intensityLight": "Light (keep more verbatim, detailed summary)",
  "prep.compact.intensityBalanced": "Balanced",
  "prep.compact.intensityAggressive": "Aggressive (keep N only, terse summary)",
  "prep.compact.directiveLabel": "Compression directive (focus)",
  "prep.compact.directivePlaceholder": "e.g. prioritize stack traces and confirmed plans…",
  "prep.compact.retainLabel": "Retained messages (auto-compact keeps the latest N verbatim)",
  // Interview prep behavior
  "prep.timeout.title": "Question dialog wait",
  "prep.timeout.desc":
    "When the coach dialog carries a recommended choice and you do not answer in time, it is auto-selected. Applies to option questions only; nothing auto-selects without a recommendation.",
  "prep.timeout.label": "Auto-select wait",
  "prep.timeout.off": "Off",
  "prep.timeout.minutes": "{n} min",
  "prep.purge.title": "Purge empty sessions",
  "prep.purge.desc": "Delete sessions that never accumulated conversation content (e.g. duplicated blank sessions); sessions with content are untouched.",
  "prep.purge.action": "Purge empty sessions",
  "prep.purge.confirmTitle": "Purge empty sessions",
  "prep.purge.confirmBody": "Delete all contentless sessions? Sessions with content are untouched; this cannot be undone.",
  "prep.purge.done": "Purged {count} empty sessions",
  "prep.purge.failed": "Purge failed",
  "prep.purgeAll.title": "Purge all sessions",
  "prep.purgeAll.desc": "Delete all conversation history, including sessions with content. This cannot be undone — proceed with care.",
  "prep.purgeAll.action": "Purge all sessions",
  "prep.purgeAll.confirmTitle": "Purge all sessions",
  "prep.purgeAll.confirmBody": "Delete all sessions and their messages? Sessions with content will also be removed; this cannot be undone.",
  "prep.purgeAll.done": "Purged {count} sessions",
  "prep.purgeAll.failed": "Purge failed",

  // Third-party integrations: link a real GitHub account (fine-grained PAT, public read-only)
  "integrations.github.title": "GitHub account linking",
  "integrations.github.desc":
    "Paste a fine-grained personal access token (public-repo read-only, 90-day expiry recommended); all agents share the authenticated quota (5,000 req/hour) instead of the anonymous one (60 req/hour). Tokens are encrypted at rest and never shown back.",
  "integrations.github.placeholder": "Paste token (github_pat_… or ghp_…), visible only this once",
  "integrations.github.saveAndTest": "Save and test",
  "integrations.github.test": "Test connection",
  "integrations.github.clear": "Clear",
  "integrations.github.saved": "Token saved",
  "integrations.github.cleared": "Token cleared",
  "integrations.github.saveFailed": "Save failed",
  "integrations.github.testPassed": "Connection works",
  "integrations.github.testFailed": "Connection failed",
  "integrations.github.configured": "Linked {tail}",
  "integrations.github.unconfigured": "Not linked (anonymous quota)",
  "integrations.github.quota": "Quota left {remaining}/{limit}",
} as const;

export type SettingsMessageKey = keyof typeof settings;
