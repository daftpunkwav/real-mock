/** 3D channel instance handle types (minimal subset of @met4citizen/talkinghead, shared by boot/gaze/emotion/mouth). */

export type HeadInstance = {
  showAvatar: (avatar: Record<string, unknown>, onprogress?: (ev: unknown) => void) => Promise<void>;
  setMood: (mood: string) => void;
  setValue: (mt: string, val: number, ms?: number | null) => void;
  setBaselineValue?: (mt: string, val: number | null) => void;
  setFixedValue?: (mt: string, val: number | null, ms?: number | null) => void;
  getMoodNames?: () => string[];
  lookAt?: (x: number, y: number, t: number) => void;
  lookAtCamera?: (t: number) => void;
  makeEyeContact?: (t: number) => void;
  stop?: () => void;
};
