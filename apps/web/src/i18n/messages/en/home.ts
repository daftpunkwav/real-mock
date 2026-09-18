/** home messages (keys must mirror zh-CN exactly; grouped by hero/features/steps/cta). */

export const home = {
  // Hero
  "hero.badge": "Open source · BYOK · Local-first",
  "hero.title.line1": "Mock interviews with",
  "hero.title.line2": "real pressure",
  "hero.sub1": "Agent-driven, multi-round voice interviews that probe your answers until they hold;",
  "hero.sub2": "per-round scoring and review reports, with your data kept local.",
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
  "features.eyebrow": "CORE FEATURES",
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
  "steps.eyebrow": "HOW IT WORKS",
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
  "cta.eyebrow": "GET STARTED",
  "cta.title": "Ready to start once configured",
  "cta.desc": "No account required; interview data stays on your device.",
  "cta.action": "Start mock interview",

  // Trust section
  "trust.eyebrow": "PRINCIPLES",
  "trust.items.local.title": "Local-first",
  "trust.items.local.desc": "Interview data and keys stay on your machine by default; no forced cloud",
  "trust.items.byok.title": "Bring your own key",
  "trust.items.byok.desc": "BYOK connects your own LLM; you control cost and model choice",
  "trust.items.opensource.title": "Open source, auditable",
  "trust.items.opensource.desc": "Transparent code and tweakable flows, easy to customize",

  // Pain-point section
  "pain.eyebrow": "WHY REALMOCK",
  "pain.title": "Most mock interviews miss the point",
  "pain.desc": "Three of the most common failure modes — and how RealMock answers each one.",
  "pain.items.bank.title": "Question banks fail",
  "pain.items.bank.desc": "Fixed question lists can't build adaptability — real interviewers keep probing your answers.",
  "pain.items.bank.feature": "Dynamic questions + follow-ups",
  "pain.items.alone.title": "Practicing blind",
  "pain.items.alone.desc": "Nobody tells you which answers fell flat, so the same blind spots follow you into the real thing.",
  "pain.items.alone.feature": "Per-round scoring + review",
  "pain.items.nerve.title": "Freezing on stage",
  "pain.items.nerve.desc": "You know the material, but organizing it into words under real pressure is a separate skill.",
  "pain.items.nerve.feature": "Live voice + multi-round flow",

  // Hero scene ring cards: objective, real interview moments in plain words
  "ring.items.role.title": "Backend engineer",
  "ring.items.role.sub": "Target role · round 1",
  "ring.items.probe.title": "Cache stampede?",
  "ring.items.probe.sub": "Probed from your answers",
  "ring.items.basics.title": "B+ tree indexes",
  "ring.items.basics.sub": "MySQL fundamentals",
  "ring.items.score.title": "82",
  "ring.items.score.sub": "Round score · clarity 3.5/5",
  "ring.items.system.title": "Flash-sale design",
  "ring.items.system.sub": "System design · whiteboard",
  "ring.items.project.title": "Project deep-dive",
  "ring.items.project.sub": "Every résumé line is fair game",
  "ring.items.hr.title": "A failure story",
  "ring.items.hr.sub": "HR round · behavioral",
  "ring.items.round.title": "Round 4 of 5",
  "ring.items.round.sub": "Multi-round flow",
  "ring.items.reverse.title": "Your questions",
  "ring.items.reverse.sub": "Ask us anything",
  "ring.items.report.title": "Review report",
  "ring.items.report.sub": "2 timeouts · tips ready",
} as const;

export type HomeMessageKey = keyof typeof home;
