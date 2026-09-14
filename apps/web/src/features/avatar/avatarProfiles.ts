/** CSS vector interviewer profiles with no external asset dependencies. */

import type { MessageKey } from "@/i18n";

/** Restrict profile labels to keys from the media namespace. */
type MediaMessageKey = MessageKey<"media">;

export interface AvatarProfile {
  /** User-visible name localized through the media namespace. */
  labelKey: MediaMessageKey;
  hair: string;
  skin: string;
  suit: string;
  shirt: string;
  accent: string;
  gender: "male" | "female";
}

export const AVATAR_PROFILES: Record<string, AvatarProfile> = {
  professional_male: {
    labelKey: "avatar.profile.professional_male",
    hair: "#2c1810",
    skin: "#e8b896",
    suit: "#1e3a5f",
    shirt: "#f1f5f9",
    accent: "#3b82f6",
    gender: "male",
  },
  senior_male: {
    labelKey: "avatar.profile.senior_male",
    hair: "#3f3f46",
    skin: "#d4a574",
    suit: "#292524",
    shirt: "#fafaf9",
    accent: "#a8a29e",
    gender: "male",
  },
  gentle_female: {
    labelKey: "avatar.profile.gentle_female",
    hair: "#4a3728",
    skin: "#f0c4a8",
    suit: "#4c1d95",
    shirt: "#faf5ff",
    accent: "#a78bfa",
    gender: "female",
  },
  hr_female: {
    labelKey: "avatar.profile.hr_female",
    hair: "#78350f",
    skin: "#f5d0b0",
    suit: "#9a3412",
    shirt: "#fff7ed",
    accent: "#fb923c",
    gender: "female",
  },
  young_female: {
    labelKey: "avatar.profile.young_female",
    hair: "#1e1b4b",
    skin: "#f3c6a8",
    suit: "#312e81",
    shirt: "#eef2ff",
    accent: "#818cf8",
    gender: "female",
  },
  strict_expert: {
    labelKey: "avatar.profile.strict_expert",
    hair: "#1a1a1a",
    skin: "#d4a574",
    suit: "#1c1917",
    shirt: "#e7e5e4",
    accent: "#ef4444",
    gender: "male",
  },
};
