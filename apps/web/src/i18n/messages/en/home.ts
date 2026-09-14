/** home messages (keys must mirror zh-CN exactly; grouped by hero/features/steps/cta). */

export const home = {
  // Hero
  "hero.badge": "Open source · BYOK · Local-first",
  "hero.title": "Open-source AI mock interview tool",
  "hero.desc":
    "Built for individual developers, runs locally. Upload a resume, pick a target role, and practice voice-based mock interviews, with a score and improvement suggestions afterwards. Bring your own LLM API key, no account required.",
  "hero.cta.interview": "Start interview",
  "hero.cta.resume": "Upload resume",

  // Hero interview preview card (demo content)
  "hero.preview.status": "Mock interview in progress",
  "hero.preview.live": "Live",
  "hero.preview.interviewerInitial": "I",
  "hero.preview.interviewer": "Interviewer",
  "hero.preview.role": "Backend engineer",
  "hero.preview.question":
    "Describe the project you worked on most recently. Focus on the decisions you made and how the results were measured.",
  "hero.preview.candidateInitial": "M",
  "hero.preview.you": "You",
  "hero.preview.answer":
    "Last quarter I reworked the order fulfillment pipeline, reducing peak latency from 320ms to 110ms and increasing QPS by 2.4x…",
  "hero.preview.videoStatus": "Video connected",
  "hero.preview.micStatus": "Transcribing",

  // Features section
  "features.title": "Key features",
  "features.desc": "Covers the full flow from interview prep to mock interviews and scored reports.",
  "features.items.dynamic.title": "Dynamic questions",
  "features.items.dynamic.desc": "Questions are generated from your resume and target role, not from a fixed question bank.",
  "features.items.probe.title": "Follow-up questions",
  "features.items.probe.desc": "Vague answers are probed for details until things are made clear.",
  "features.items.company.title": "Company styles",
  "features.items.company.desc": "Question style and focus can be adjusted to match different companies' interview styles.",
  "features.items.av.title": "Audio and video",
  "features.items.av.desc": "Real-time conversations via voice and camera.",
  "features.items.prep.title": "Interview prep",
  "features.items.prep.desc": "Review key points before the session, with interview-experience search.",
  "features.items.report.title": "Reports and growth",
  "features.items.report.desc": "Each session produces a score and improvement suggestions; past sessions can be reviewed.",

  // Steps section
  "steps.title": "How it works",
  "steps.desc": "Configure your key and upload a resume to start a mock interview.",
  "steps.items.key.title": "Add your key",
  "steps.items.key.desc": "Configure your own LLM API key in Settings; stored locally with encryption",
  "steps.items.resume.title": "Upload resume",
  "steps.items.resume.desc": "Your resume is parsed and used as the basis for interview questions",
  "steps.items.interview.title": "Start an interview",
  "steps.items.interview.desc": "Choose a role and company, then enter a voice mock interview",
  "steps.go": "Go",

  // CTA section
  "cta.title": "Ready to start once configured",
  "cta.desc": "No account required; interview data stays on your device.",
  "cta.action": "Start mock interview",

  // Trust section
  "trust.items.local.title": "Local-first",
  "trust.items.local.desc": "Interview data and keys stay on your machine by default; no forced cloud",
  "trust.items.byok.title": "Bring your own key",
  "trust.items.byok.desc": "BYOK connects your own LLM; you control cost and model choice",
  "trust.items.opensource.title": "Open source, auditable",
  "trust.items.opensource.desc": "Transparent code and tweakable flows, easy to customize",
} as const;

export type HomeMessageKey = keyof typeof home;
