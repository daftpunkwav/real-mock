/** media 文案(录音/TTS 与数字人两域共用,recorder. / avatar. 前缀区分;key 用点分路径,zh-CN 为 key 源)。 */

export const media = {
  // recorder(录音)
  "recorder.micUnavailable": "麦克风不可用",

  // avatar(数字人)
  "avatar.profile.professional_male": "专业男面试官",
  "avatar.profile.senior_male": "资深男面试官",
  "avatar.profile.gentle_female": "亲和女面试官",
  "avatar.profile.hr_female": "HR 女面试官",
  "avatar.profile.young_female": "青年女面试官",
  "avatar.profile.strict_expert": "严厉专家",
  "avatar.loading3d": "加载 3D 面试官…",
  "avatar.loading3dHint": "不阻塞进房与麦克风",
  "avatar.stage3dFallback": "3D 人像加载失败，已回退平面形象",
  "avatar.emotionSmile": "友好",
  "avatar.emotionSerious": "严肃",
} as const;

export type MediaMessageKey = keyof typeof media;
