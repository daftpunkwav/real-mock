/**
 * @file resume.ts
 * @description resume messages (resume management: upload / list / deep review / file preview; keys mirror zh-CN).
 */

export const resume = {
  // Page shell
  "page.loading": "Loading…",
  "head.eyebrow": "Resume",
  "head.title": "Resume",

  // ResumeUploadArea: upload zone
  "upload.parsing": "Parsing resume…",
  "upload.cta": "Click or drag to upload a resume",
  "upload.formats": "PDF · DOCX · MD · TXT · Max 10MB",

  // ResumeList: list
  "list.title": "My Resumes",
  "list.count": "{count} total",
  "list.empty": "No resumes yet. Upload one first.",

  // ResumeListItem: list item and action bar
  "item.chipActive": "Active",
  "item.scoreChip": "Score {score}",
  "item.currentActive": "Current",
  "item.setActive": "Set as active",
  "item.analyzing": "Reviewing…",
  "item.analyze": "AI Deep Review",
  "item.delete": "Delete",
  "item.deleteTitle": "Delete resume",
  "item.deleteConfirm": "Delete version \"{name}\"? Other versions in the family are kept.",
  "item.versionChip": "v{n}",
  "item.latestIdle": "Latest, not active",
  "item.uploadVersion": "Upload new version",

  // ResumeDetailPanel: deep review area
  "detail.analyzingBanner":
    "The reviewer Agent is running; this page will refresh when it finishes…",
  "detail.emptySelect": "Select a resume to see its review",
  "detail.none": "No deep review yet",
  "detail.noneHint": "Once generated, it covers layout, typography and content in full",
  "detail.start": "Start review",

  // AnalyzeStageProgress: live Agent plan
  "stage.waiting": "The reviewer is deciding the next step…",
  "stage.plan": "Plan",
  "stage.parallel": "Parallel",
  "stage.parallelHint": "Batched with peer parallel steps",
  "stage.log": "Execution",
  "stage.emptyLog": "Waiting for the first step…",
  "stage.thinking": "Thinking",
  "stage.thinkingActive": "Thinking…",
  "stage.thinkingDuration": "lasted {seconds}s",
  "stage.toolName": "Tool",
  "stage.toolFallback": "Tool",
  "stage.toolName.web_search": "Search the web",
  "stage.toolName.resume_overview": "Read resume overview",
  "stage.toolName.resume_get_section": "Read resume section",
  "stage.toolName.profile_list_sections": "List profile sections",
  "stage.toolName.profile_get_section": "Read profile details",
  "stage.toolName.github_get_user": "Look up GitHub user",
  "stage.toolName.github_list_repos": "List GitHub repositories",
  "stage.toolName.github_get_repo": "Inspect GitHub repository",
  "stage.toolName.github_get_readme": "Read repository README",
  "stage.toolName.github_get_file": "Read repository source",
  "stage.toolName.github_get_languages": "Inspect repository languages",
  "stage.toolName.github_list_pulls": "Inspect repository pull requests",
  "stage.toolName.github_list_issues": "Inspect repository issues",
  "stage.toolName.github_list_commits": "Inspect repository commits",
  "stage.toolStatus.running": "Running",
  "stage.toolStatus.done": "Done",
  "stage.toolStatus.error": "Failed",
  "stage.sites": "Sites",
  "stage.args": "Arguments",
  "stage.result": "Result",

  // AnalysisPanel: deep review sheet
  "analysis.mastheadTitle": "Agent Deep Review",
  "analysis.mastheadSub": "Resume review notes",
  "analysis.tabsAria": "Review sections",
  "analysis.tab.overview": "Overview",
  "analysis.tab.document": "Layout & Structure",
  "analysis.tab.projects": "Project Deep-Dive",
  "analysis.tab.interview": "Interview Drill",
  "analysis.tab.advice": "Resume Advice",
  "analysis.tab.career": "Career & Market",

  // Deep review dimension labels (DIM_LABEL_KEYS)
  "dim.structure_clarity": "Structure",
  "dim.visual_layout": "Layout",
  "dim.typography": "Readability",
  "dim.impact_quantification": "Quantified Impact",
  "dim.tech_depth": "Tech Depth",
  "dim.project_narrative": "Project Story",
  "dim.role_fit": "Role Fit",
  "dim.keyword_ats": "ATS Keywords",
  "dim.credibility": "Credibility",
  "dim.seniority_signal": "Seniority",
  "dim.growth_signal": "Growth Potential",
  "dim.collaboration_signal": "Collaboration",

  // OverviewTab / ImpressionCards: overview
  "overview.narrative": "Overall",
  "overview.seniorityPrefix": "Seniority · ",
  "overview.roleFit": "Role Fit",
  "overview.radar": "Ability Radar",
  "overview.headlineTag": "One-line Persona",
  "overview.impressionTag": "Interviewer's 30-Second First Impression",
  "overview.notesTitle": "Interviewer's Desk Notes",
  "overview.percentileTitle": "Score rank",
  "overview.percentileBefore": "Maps to about ",
  "overview.percentileAfter": " on a score-derived scale",
  "overview.percentileDisclaimer": "Converted from the overall score; not a real peer sample.",
  "overview.seniorityLabel": "Seniority",
  "overview.dimTable": "Dimension scores",
  "overview.dimName": "Dimension",
  "overview.dimScore": "Score",
  "overview.dimBand": "Band",
  "overview.dimWeight": "Weight",
  "overview.band.standout": "Standout",
  "overview.band.solid": "Solid",
  "overview.band.mixed": "Mixed",
  "overview.band.weak": "Weak",
  "overview.compareTitle": "Version gap",
  "overview.compareScores": "Overall by version",
  "overview.compareDeltas": "Change vs previous version",
  "overview.compareOverall": "Overall {prev} → {curr} ({delta})",
  "overview.compareDimsMissing": "Previous version lacks dimension detail; comparing overall score only.",
  "overview.compareOverlay": "Radar overlay",
  "overview.scaleLow": "Low",
  "overview.scaleMid": "Mid",
  "overview.scaleHigh": "High",

  // RadarChart / ScoreRing
  "radar.aria": "Dimension ability radar chart",
  "ring.aria": "Overall score {score}",
  "ring.label": "Overall",

  // ProjectsTab / ProjectCards: project deep-dive
  "projects.evidence": "Open-source Repo Evidence",
  "projects.unknownRepo": "Unknown repo",
  "projects.lastPush": "Last push {date}",
  "projects.verification": "Claims vs. Repo Facts",
  "projects.cardsTitle": "Project Deep-Dive Cards",
  "projects.highlight": "Highlights",
  "projects.risk": "Risks",
  "projects.mustAsk": "Must-Ask Questions",
  "projects.deepDive": "Project Deep-Dive Points",

  // SkillTrustBoard (advice) / SectionHeatmap (document) / CareerPanel (career)
  "advice.trustBoard": "Skill Trust Board",
  "document.heatTitle": "Section Review Heatmap",
  "document.heatAria": "Resume section review",
  "trust.solid.title": "Proven Skills",
  "trust.solid.hint": "Backed by projects and numbers; safe to lead with in interviews",
  "trust.claimed.title": "Listed Only",
  "trust.claimed.hint": "Appears only in the skill list; wears thin under follow-up questions",
  "trust.missing.title": "Missing for Role",
  "trust.missing.hint": "Frequently required for the target role but absent from the resume",
  "career.title": "Career Trajectory Analysis",
  "career.gaugeAria": "Direction focus {score}",
  "career.gaugeLabel": "Focus",
  "career.gaps": "Timeline Questions",

  // DocumentTab
  "document.layout": "Layout & Structure",
  "document.typography": "Typography & Readability",
  "document.content": "Content Depth",

  // InterviewTab: interview drill
  "interview.qaTitle": "Predicted Q&A Cards",
  "interview.qaIntent": "Interviewer intent",
  "interview.qaPoints": "Model answer points",
  "interview.qaFollowUps": "Likely follow-ups",
  "interview.predicted": "Predicted Interview Questions",
  "interview.riskAreas": "Probe-Prone Areas",

  // AdviceTab: resume advice
  "advice.strengths": "Strengths",
  "advice.weaknesses": "Weaknesses",
  "advice.redFlags": "Red Flags",
  "advice.improvements": "Improvement Suggestions",
  "advice.coveredKeywords": "Covered Keywords",
  "advice.suggestedKeywords": "Suggested Additions",

  // CareerTab: career and market
  "career.salary": "Salary Positioning",
  "career.companyFit": "Company-Tier Fit",
  "career.market": "Market Insights",

  // RewriteGallery: rewrite examples
  "rewrite.title": "Rewrite Examples",
  "rewrite.before": "Before",
  "rewrite.after": "After",

  // ResumePreviewCard: compact preview card
  "previewCard.title": "Resume Preview",
  "previewCard.nameUnknown": "Name not parsed",
  "previewCard.open": "Preview File",
  "previewCard.score": "AI Score",
  "previewCard.summary": "Summary",
  "previewCard.skills": "Skills",
  "previewCard.projects": "Projects",
  "previewCard.projectUnnamed": "Untitled project",
  "previewCard.empty": "Upload to see the preview",

  // ResumeOverviewCard / ResumeTipsCard: overview and tips
  "overviewCard.title": "Overview",
  "overviewCard.uploaded": "Uploaded",
  "overviewCard.scored": "Scored",
  "overviewCard.active": "Active:",
  "tips.title": "Tips",
  "tips.first": "· \"Set as active\" links the resume to mock interviews and interview prep",
  "tips.second":
    "· Deep review searches job requirements online and reviews layout, typography and content",
  "tips.third":
    "· Older reviews only refresh to the new structure after clicking \"AI Deep Review\" again",

  // ResumeFilePreview / PreviewToolbar: standalone file preview
  "preview.nameFallback": "Resume",
  "preview.pageAlt": "{name} page {page}",
  "preview.pages": "Page {current} / {total}",
  "preview.zoomOut": "Zoom out",
  "preview.zoomIn": "Zoom in",
  "preview.fitWidth": "Fit width",
  "preview.download": "Download",
  "preview.downloadFile": "Download file",
  "preview.loadFailed": "Preview failed to load; download it to view.",
  "preview.unsupported": "This format can't be previewed inline; download it to view.",

  // useResumeList / previewRoute: error fallbacks and toasts
  "hook.loadFailed": "Load failed",
  "toast.uploaded": "Resume uploaded and parsed",
  "toast.uploadedFallback":
    "Resume uploaded, but structured parsing fell back to a raw-text summary. Deep review can still run.",
  "toast.uploadFailed": "Upload failed",
  "toast.listRefreshFailed":
    "Change saved, but the list could not be refreshed. Reload the page.",
  "toast.parallelLimit": "At most {count} resumes can be reviewed in parallel; wait for one to finish",
  "toast.analyzing":
    "Generating deep review for \"{name}\" (Agent tools + web lookup); takes about 2–4 minutes, up to {count} at a time…",
  "toast.analyzingUnnamed":
    "Generating deep review (Agent tools + web lookup); takes about 2–4 minutes, up to {count} at a time…",
  "toast.analyzeDone": "Review done · Overall score {score}",
  "toast.analyzeFailed": "Analysis failed",
  "toast.activated": "Set as the resume for applications",
  "toast.activateFailed": "Failed to set for applications",
  "toast.versionCap": "This family already has {count} versions",
  "toast.deleted": "Deleted",
  "toast.deleteFailed": "Delete failed",
} as const;

export type ResumeMessageKey = keyof typeof resume;
