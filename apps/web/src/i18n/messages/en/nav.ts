/** Sidebar navigation strings (labelKey in config/nav.ts points here). */

export const nav = {
  "aria.main": "Main navigation",
  "items.home": "Home",
  "items.profile": "Profile",
  "items.resume": "Resume",
  "items.prep": "Interview Prep",
  "items.interview": "Mock Interview",
  "items.history": "History",
  "items.growth": "Growth",
  "items.settings": "Settings",
} as const;

export type NavMessageKey = keyof typeof nav;
