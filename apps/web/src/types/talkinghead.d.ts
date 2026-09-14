declare module "@met4citizen/talkinghead" {
  export class TalkingHead {
    constructor(node: HTMLElement, opt?: Record<string, unknown>);
    showAvatar(
      avatar: Record<string, unknown>,
      onprogress?: (ev: unknown) => void,
    ): Promise<void>;
    setMood(mood: string): void;
    setValue(mt: string, val: number, ms?: number | null): void;
    getMoodNames(): string[];
    lookAt(x: number, y: number, t: number): void;
    stop(): void;
  }
}
