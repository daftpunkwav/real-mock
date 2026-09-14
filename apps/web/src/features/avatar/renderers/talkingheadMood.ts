import type { TalkingMood } from "./talkingheadAssets";

const VALID_MOODS: ReadonlySet<TalkingMood> = new Set([
  "neutral",
  "happy",
  "angry",
  "sad",
  "fear",
  "disgust",
  "love",
  "sleep",
]);

export function safeMood(mood: string | undefined, fallback: TalkingMood = "neutral"): TalkingMood {
  if (mood && VALID_MOODS.has(mood as TalkingMood)) return mood as TalkingMood;
  return fallback;
}

/** Expression → The inner mood of the library (when the mood granularity is not enough, the auxiliary morph will add a layer). */
export const EXPRESSION_TO_MOOD: Record<string, TalkingMood> = {
  neutral: "neutral",
  smile: "happy",
  happy: "happy",
  serious: "neutral",
  curious: "neutral",
  encouraging: "happy",
  skeptical: "fear",
  concerned: "sad",
  angry: "angry",
  sad: "sad",
};

/** Expression → Auxiliary morph (eyebrows/eyes/mouth corners). */
export const EXPRESSION_MORPH: Record<
  string,
  { browInnerUp?: number; eyeSquint?: number; mouthSmile?: number; eyesClosed?: number }
> = {
  neutral: {},
  smile: { mouthSmile: 0.45, eyeSquint: 0.15 },
  happy: { mouthSmile: 0.55, eyeSquint: 0.2 },
  serious: { browInnerUp: 0.35, mouthSmile: 0 },
  curious: { browInnerUp: 0.4, mouthSmile: 0.1 },
  encouraging: { mouthSmile: 0.4, eyeSquint: 0.12 },
  skeptical: { browInnerUp: 0.25, mouthSmile: 0 },
  concerned: { browInnerUp: 0.45, mouthSmile: 0, eyesClosed: 0.08 },
  angry: { browInnerUp: 0.55, mouthSmile: 0 },
  sad: { browInnerUp: 0.3, mouthSmile: 0, eyesClosed: 0.12 },
};
