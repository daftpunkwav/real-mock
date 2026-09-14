/** 3D channel homologous GLB assets and rendering customizations for that channel (baseline pose/lighting/default mood). */

/** Library built-in mood name (no serious; values ​​not listed will fall back to neutral). */
export type TalkingMood =
  | "neutral"
  | "happy"
  | "angry"
  | "sad"
  | "fear"
  | "disgust"
  | "love"
  | "sleep";

interface TalkingHeadAsset {
  url: string;
  body: "M" | "F";
  mood: TalkingMood;
  baseline?: Record<string, number>;
  light?: { ambient: number; direct: number; directColor: number };
}

export const AVATAR_ASSETS: Record<string, TalkingHeadAsset> = {
  professional_male: {
    url: "/avatars/professional_male.glb",
    body: "M",
    mood: "neutral",
    baseline: {
      headRotateX: 0.12,
      eyesLookDown: 0,
      eyesLookUp: 0.08,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 1.25, direct: 8, directColor: 0xffe6cc },
  },
  senior_male: {
    url: "/avatars/senior_male.glb",
    body: "M",
    mood: "neutral",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.06,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 1.05, direct: 9, directColor: 0xffd8b0 },
  },
  strict_expert: {
    url: "/avatars/senior_male.glb",
    body: "M",
    mood: "angry",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.05,
      browInnerUp: 0.15,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 0.9, direct: 11, directColor: 0xffd0b0 },
  },
  gentle_female: {
    url: "/avatars/gentle_female.glb",
    body: "F",
    mood: "happy",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.08,
      mouthSmile: 0.15,
    },
    light: { ambient: 1.3, direct: 7.5, directColor: 0xffeef0 },
  },
  hr_female: {
    url: "/avatars/hr_female.glb",
    body: "F",
    mood: "neutral",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.07,
    },
    light: { ambient: 1.2, direct: 8, directColor: 0xffe8d8 },
  },
  young_female: {
    url: "/avatars/young_female.glb",
    body: "F",
    mood: "happy",
    baseline: {
      headRotateX: 0.11,
      eyesLookDown: 0,
      eyesLookUp: 0.09,
      mouthSmile: 0.2,
    },
    light: { ambient: 1.35, direct: 7, directColor: 0xfff0e8 },
  },
};
