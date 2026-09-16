/** interview messages (keys mirror zh-CN exactly; placeholders must match). */

export const interview = {
  // ---- Setup: shell / start button / loading & errors ----
  "setup.eyebrow": "Mock Setup",
  "setup.title": "Configure Mock Interview",
  "setup.start": "Start Mock Interview",
  "setup.loading": "Loading configuration…",
  "setup.loadFailed": "Load failed",
  "setup.createFailed": "Failed to create",

  // ---- Setup: form fields ----
  "setup.role.label": "Target role",
  "setup.role.custom": "Custom role",
  "setup.role.customPlaceholder": "Enter job title",
  "setup.role.customRequired": "Please enter a custom job title",
  "setup.level.label": "Level",
  "setup.type.label": "Interview type",
  "setup.style.label": "Interview style",
  "setup.company.label": "Target company",
  "setup.company.custom": "Custom company",
  "setup.company.customPlaceholder": "Enter company name",
  "setup.company.customRequired": "Please enter the custom company name",
  "setup.company.customNote": "AI will research this company's interview process and preferences online to tailor the interview",
  "setup.personality.label": "Interviewer personality",
  "setup.strictness.label": "Strictness {n}/10 · {label}",
  "setup.strictness.friendly": "Friendly",
  "setup.strictness.normal": "Balanced",
  "setup.strictness.high": "High pressure",
  "setup.strictness.extreme": "Extreme",
  "setup.avatar.label": "Interviewer avatar",
  "setup.avatar.voiceMatch": "{name} (voice: {voice})",
  "setup.scene.label": "Scene",
  "setup.resume.label": "Resume",
  "setup.resume.activeItem": "{name} (applied)",
  "setup.resume.empty": "No resume yet; you can upload one later in Resume Manager",

  // ---- Setup: processor card ----
  "setup.processor.title": "Processors & reasoning effort",
  "setup.processor.chatModel": "Reasoning model",
  "setup.processor.effort": "Reasoning effort",
  "setup.processor.stt": "Voice input (recognition)",
  "setup.processor.tts": "Voice output (playback)",
  "setup.processor.sttAria": "Voice input model",
  "setup.processor.ttsAria": "Voice output model",
  "setup.processor.referenceDetail": "Reference answer",
  "setup.processor.referenceOutline": "Outline (fast)",
  "setup.processor.referenceFull": "Full answer (slower, richer)",

  // ---- Setup: preview column ----
  "preview.title": "Preview",
  "preview.row.role": "Role",
  "preview.row.company": "Company",
  "preview.row.type": "Type",
  "preview.row.interviewer": "Interviewer",
  "preview.row.avatar": "Avatar",
  "preview.row.resume": "Resume",
  "preview.row.resumeEmpty": "Not linked (generic questions, weaker deep dives)",
  "preview.voice": "Voice {name}",
  "preview.companyQuestions": "{name} · Question style",
  "preview.style": "Style",
  "preview.focus": "Focus areas",
  "preview.process": "Smart flow",
  "preview.flow.badge": "AI planned",
  "preview.flow.desc":
    "Fixed opening and closing; middle blocks are planned by AI from resume projects, role/level, company style, and prior rounds (8–30 themed blocks, not a fixed order).",
  "preview.flow.opening": "Fixed opening",
  "preview.flow.openingDesc": "Identity · Self intro",
  "preview.flow.custom": "AI planned",
  "preview.flow.customDesc": "Project dives · technical probes",
  "preview.flow.coverage": "Baseline coverage (actual outline appears after kickoff)",
  "preview.flow.closing": "Q&A · Wrap-up",
  "preview.flow.closingDesc": "Your questions · verdict",
  "preview.flow.note":
    "At least one deep-dive block per resume project; later rounds skip covered topics. Falls back to the baseline when planning fails.",
  "preview.flow.noResume":
    "No resume linked: AI falls back to generic questions with weaker deep dives. Link a resume first.",
  "preview.sampleLabel": "Sample probe",
  "preview.samplePrefix": "Sample:",
  "preview.tip":
    "Link a resume for at least one deep dive per project; multi-round flows skip already-covered topics.",

  // ---- Room: turn states ----
  "status.turn.aiSpeaking": "Interviewer speaking",
  "status.turn.userSpeaking": "Your turn to answer",
  "status.turn.processing": "Thinking",
  "status.turn.idle": "Standby",

  // ---- Room: entry gates / connection states ----
  "room.gate.invalidSession.title": "Invalid session ID",
  "room.gate.invalidSession.desc": "Please start a new interview from the setup page.",
  "room.gate.tokenMissing.title": "Session invalid or access denied",
  "room.gate.tokenMissing.desc":
    "Please start a new interview from the setup page. Opening a history link directly may miss the capability-token cookie.",
  "room.gate.connectFailed.title": "Cannot reach the interview service",
  "room.gate.connectFailed.desc":
    "Failed after 5 attempts. Make sure the backend is running (default :8081) or check your network.",
  "room.gate.backToSetup": "Back to setup page",
  "room.gate.backToSetupShort": "Back to setup",
  "room.gate.reconnect": "Reconnect",
  "room.connecting.connecting": "Connecting to interview service…",
  "room.connecting.reconnecting": "Reconnecting…",

  // ---- Phase display names (aligned with config/phases.ts / backend SSOT; UI uses these) ----
  "phase.identity_check": "Identity check",
  "phase.self_intro": "Self introduction",
  "phase.basic_knowledge": "Fundamentals",
  "phase.project_deep_dive": "Project deep dive",
  "phase.technical_deep": "Technical deep dive",
  "phase.system_design": "System design",
  "phase.scenario": "Scenario questions",
  "phase.reverse_qa": "Your questions",
  "phase.summary": "Summary",
  "phase.career_plan": "Career plans",
  "phase.teamwork": "Teamwork",
  "phase.pressure": "Pressure questions",
  "phase.salary": "Compensation",
  "phase.leadership": "Leadership",
  "phase.decision_making": "Decision making",
  "phase.conflict": "Conflict handling",
  "phase.business": "Business sense",

  // ---- Room: header / connection banners ----
  "room.header.session": "Interview #{id}",
  "room.phase.preparing": "Preparing",
  "room.conn.disconnected": "Connection lost",
  "room.conn.retry": "Retry",
  "room.conn.reconnecting": "Connection lost, reconnecting…",
  "room.conn.attempt": "(attempt {n})",

  // ---- Room: audio unlock ----
  "room.audio.unlockTitle": "Enable interviewer audio",
  "room.audio.unlockDesc":
    "Browsers block autoplay without a user gesture. Click the button below to unlock audio so the interviewer's opening line can play.",
  "room.audio.unlockButton": "Enable audio and start",
  "room.audio.blockedBanner": "No sound? Your browser may have blocked autoplay",
  "room.audio.enableAndRetry": "Enable and retry",
  "room.audio.reunlock": "Unlock audio again",
  "room.audio.enable": "Enable audio",

  // ---- Room: finishing ----
  "room.finish.button": "End interview",
  "room.finish.finishing": "Wrapping up…",
  "room.finish.playingClosing": "Playing the closing review; jumping to the report when done…",

  // ---- Room: chat column ----
  "chat.empty.restored": "Session restored; waiting for your answer",
  "chat.empty.starting": "The interview is about to start; keep your face in view",
  "chat.input.placeholder": "Type your answer, or speak into the mic…",
  "chat.input.waiting": "Waiting for the interviewer…",
  "chat.send.text": "Send text",
  "chat.send.voice": "Send voice",
  "chat.send.hint": "Type or speak first",
  "chat.bubble.me": "Me",
  "chat.bubble.ai": "AI",
  "chat.bubble.candidate": "Candidate",
  "chat.bubble.interviewer": "Interviewer",
  "chat.bubble.interviewerNudge": "Interviewer · follow-up",
  "chat.bubble.streamingSuffix": " · typing",
  "chat.thinking": "The interviewer is thinking…",
  "chat.timer.think": "Think time {time}",
  "chat.timer.answer": "Answer time {time}",

  // ---- Room: video panel / face status ----
  "video.mic.off": "Mic off",
  "video.face.initial": "Not detected",
  "video.camera.off": "Camera is off",
  "video.camera.turnOn": "Turn camera on",
  "video.camera.turnOff": "Turn camera off",
  "video.camera.permissionDenied": "Camera permission denied",
  "video.waitingTurn": "Waiting for your turn…",
  "video.face.lookingAway": "Face detected · not looking at the camera",
  "video.face.nervous": "Face detected · slightly tense",
  "video.face.normal": "Face detected · looking good",
  "video.face.none": "No face detected",
  "video.face.unavailable": "Face analysis temporarily unavailable",
  "video.face.noDetectorApi": "Camera on (browser does not support the Face Detector API)",

  // ---- Room: reference answer ----
  "room.outline.title": "Reference answer",
  "room.outline.tabCoding": "Code whiteboard",
  "room.outline.tabReference": "Reference answer",
  "room.outline.regenerateTitle": "Regenerate the reference answer for the interviewer's latest question",
  "room.outline.regenerate": "Regenerate",
  "room.outline.toggle": "Show reference",
  "room.outline.replyChars": "Reply chars",
  "room.outline.hidden": "Reference answer hidden — hard mode, you're on your own",
  "room.outline.sourcesPrefix": "Sources: ",
  "room.outline.generating": "AI is generating the reference answer…",
  "room.outline.forQuestion": "Regarding: {q}",
  "room.outline.placeholder": "After the interviewer asks, AI will generate reference answer points from your resume.",
  "room.source.resume": "Resume",
  "room.source.github": "GitHub",
  "room.source.companyKb": "Company KB",
  "room.hint.timeout":
    "Generation is slow or timed out. Try STAR: Situation → Task → Action → Result (quantify where possible).",
  "room.hint.timeoutDetailed":
    "Full-answer generation timed out. Tap regenerate to retry the full version.",

  // ---- Room: toasts / voice status (non-render paths) ----
  "room.toast.audioEnabled": "Audio enabled",
  "room.toast.audioEnableFailed": "Could not enable audio; check browser permissions",
  "room.toast.finishDisconnected": "Connection lost; couldn't end the interview. Please retry.",
  "room.toast.finishing": "The interviewer is wrapping up the evaluation…",
  "room.toast.ttsFailed": "Voice playback failed",
  "room.toast.interruptedCount": "Interrupted the speaker ({n} times total; affects the politeness score)",
  "room.toast.interrupted": "Interrupted the interviewer",
  "room.toast.sttFailed": "Recognition failed; you can continue by typing below",
  "room.msg.warning": "⚠️ {msg}",
  "room.voice.error": "Error: {msg}",
  "room.voice.waitingTurn": "Waiting for your turn",
  "room.voice.bargeWithText": "Barge-in ready · hearing \"{text}\"",
  "room.voice.bargeHint": "Interviewer speaking · you can interrupt (affects the politeness score)",
  "room.voice.recognizing": "Recognizing \"{text}\"",
  "room.voice.listening": "Listening; pause for about 1 second to auto-send, or press send",
  "room.voice.startingMic": "Starting microphone…",

  // ---- Setup option catalogs (ids from backend; display only via i18n) ----
  "options.role.backend_engineer": "Backend Engineer",
  "options.role.frontend_engineer": "Frontend Engineer",
  "options.role.fullstack_engineer": "Full-stack Engineer",
  "options.role.ai_engineer": "AI Engineer",
  "options.role.algorithm_engineer": "Algorithm Engineer",
  "options.role.game_client_engineer": "Game Client Engineer",
  "options.role.game_server_engineer": "Game Server Engineer",
  "options.role.mobile_engineer": "Mobile Engineer",
  "options.role.devops_engineer": "DevOps Engineer",
  "options.role.product_manager": "Product Manager",
  "options.role.engineering_manager": "Engineering Manager",

  "options.level.intern": "Intern",
  "options.level.junior_engineer": "Junior Engineer",
  "options.level.mid_engineer": "Mid-level Engineer",
  "options.level.senior_engineer": "Senior Engineer",
  "options.level.expert": "Expert",
  "options.level.architect": "Architect",

  "options.personality.gentle": "Gentle",
  "options.personality.gentle.desc": "Warm and supportive, with light guidance",
  "options.personality.professional": "Professional",
  "options.personality.professional.desc": "Precise and rigorous, depth-focused",
  "options.personality.pressure": "Pressure",
  "options.personality.pressure.desc": "High-pressure probing, stress-interview style",
  "options.personality.hr": "HR",
  "options.personality.hr.desc": "Soft skills and culture fit",
  "options.personality.expert": "Technical expert",
  "options.personality.expert.desc": "Deep technical focus on fundamentals",

  "options.style.guided": "Guided",
  "options.style.deep_dive": "Deep dive",
  "options.style.continuous": "Continuous probing",
  "options.style.challenging": "Challenging",

  "options.workflow.technical": "Technical Interview",
  "options.workflow.hr": "HR Interview",
  "options.workflow.management": "Management Interview",

  "options.scene.meeting_room": "Corporate meeting room",
  "options.scene.glass_office": "Glass-partition office",
  "options.scene.online_interview": "Online interview room",
  "options.scene.boardroom": "Boardroom",
  "options.scene.startup_loft": "Startup open loft",
  "options.scene.library_corner": "Quiet meeting corner",

  "options.voice.zh-CN-XiaoxiaoNeural": "Xiaoxiao (female)",
  "options.voice.zh-CN-YunxiNeural": "Yunxi (male)",
  "options.voice.zh-CN-YunyangNeural": "Yunyang (professional male)",
  "options.voice.zh-CN-XiaoyiNeural": "Xiaoyi (lively female)",
  "options.voice.zh-CN-YunjianNeural": "Yunjian (steady male)",

  "options.company.bytedance.name": "ByteDance",
  "options.company.bytedance.style":
    "High-frequency probing, strong project deep-dives, business thinking and quantified impact",
  "options.company.bytedance.focus":
    "Project deep dive|Business thinking|Performance optimization|System design|Algorithms",
  "options.company.bytedance.sample0":
    "You mentioned optimizing API performance — what were the QPS numbers before and after?",

  "options.company.tencent.name": "Tencent",
  "options.company.tencent.style":
    "Solid fundamentals, project experience, teamwork and incident handling",
  "options.company.tencent.focus":
    "Fundamentals|Project experience|Teamwork|Incident handling|Code quality",
  "options.company.tencent.sample0":
    "If a major production incident happens, how do you locate and resolve it?",

  "options.company.alibaba.name": "Alibaba",
  "options.company.alibaba.style": "Business thinking, technical depth, and values fit",
  "options.company.alibaba.focus":
    "Business thinking|Technical depth|Distributed systems|High concurrency|Values",
  "options.company.alibaba.sample0":
    "How do you understand the core pain point of this business scenario?",

  "options.company.meituan.name": "Meituan",
  "options.company.meituan.style": "Engineering ability, business delivery, and problem solving",
  "options.company.meituan.focus":
    "Engineering practice|Business delivery|Performance optimization|Data-driven decisions",
  "options.company.meituan.sample0": "How do you use data to drive technical decisions?",

  "options.company.mihoyo.name": "miHoYo",
  "options.company.mihoyo.style":
    "Project experience, engine understanding, performance, and game-dev passion",
  "options.company.mihoyo.focus":
    "Game engines|Performance optimization|Rendering pipeline|Project experience|GC / memory",
  "options.company.mihoyo.sample0":
    "How would you investigate stuttering caused by GC in Unity?",

  "options.company.openai.name": "OpenAI",
  "options.company.openai.style":
    "Technical depth, research ability, system design, and AI/ML expertise",
  "options.company.openai.focus":
    "Machine learning|System design|Coding ability|Research mindset|Engineering practice",
  "options.company.openai.sample0":
    "Design a distributed training system for large language models.",

  "options.company.google.name": "Google",
  "options.company.google.style": "Algorithms, system design, leadership, and Googleyness",
  "options.company.google.focus": "Algorithms|System design|Code quality|Leadership|Innovation",
    // Multi-round interview process
  "setup.rounds.label": "Rounds",
  "setup.rounds.single": "Single round",
  "setup.rounds.multi": "Multi-round (up to 5)",
  "process.title": "Continue interview process",
  "process.kind.tech_1": "Technical R1",
  "process.kind.tech_2": "Technical R2",
  "process.kind.tech_deep": "Tech Addendum",
  "process.kind.hr_1": "HR R1",
  "process.kind.hr_2": "HR R2",
  "process.kind.mgmt": "Hiring Manager",
  "process.kind.cross": "Final Loop",
  "process.roundN": "Round {n}",
  "process.next": "Start round {n}",
  "process.nextFailed": "Failed to start the next round",
  "room.verdict.passed": "Interviewer verdict: you passed this round",
  "room.verdict.failed": "Interviewer verdict: you did not pass this round",
  "options.company.google.sample0": "Design Google Maps routing algorithm at scale.",
} as const;

export type InterviewMessageKey = keyof typeof interview;
