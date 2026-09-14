/** media messages (recorder/TTS and avatar share this namespace, disambiguated by recorder./avatar. prefixes). */

export const media = {
  // recorder (microphone capture)
  "recorder.micUnavailable": "Microphone unavailable",

  // avatar (digital human)
  "avatar.profile.professional_male": "Professional Male Interviewer",
  "avatar.profile.senior_male": "Senior Male Interviewer",
  "avatar.profile.gentle_female": "Friendly Female Interviewer",
  "avatar.profile.hr_female": "HR Female Interviewer",
  "avatar.profile.young_female": "Young Female Interviewer",
  "avatar.profile.strict_expert": "Strict Expert",
  "avatar.loading3d": "Loading 3D interviewer…",
  "avatar.loading3dHint": "Won't block joining the room or the mic",
  "avatar.stage3dFallback": "3D portrait failed to load; fell back to the flat portrait",
  "avatar.emotionSmile": "Friendly",
  "avatar.emotionSerious": "Serious",
} as const;

export type MediaMessageKey = keyof typeof media;
