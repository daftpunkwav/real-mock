import { describe, expect, it } from "vitest";

import { mergeRestoredMessages } from "../messages";
import type { ChatMessage } from "@/lib/api/contract";

function turn(role: ChatMessage["role"], content: string): ChatMessage {
  return { role, content };
}

describe("mergeRestoredMessages", () => {
  it("uses history when nothing has arrived live yet", () => {
    const history = [turn("assistant", "hello"), turn("user", "hi")];
    expect(mergeRestoredMessages(history, [])).toEqual(history);
  });

  it("keeps live turns that the snapshot does not have yet", () => {
    const history = [turn("assistant", "hello")];
    const live = [turn("assistant", "hello"), turn("user", "answer")];
    expect(mergeRestoredMessages(history, live)).toEqual(live);
  });

  it("prepends older history without duplicating the overlap", () => {
    const history = [turn("assistant", "q1"), turn("user", "a1")];
    const live = [turn("user", "a1"), turn("assistant", "q2")];
    expect(mergeRestoredMessages(history, live)).toEqual([
      turn("assistant", "q1"),
      turn("user", "a1"),
      turn("assistant", "q2"),
    ]);
  });

  it("keeps the longer snapshot when live is only its opening", () => {
    const history = [turn("assistant", "opening"), turn("user", "answer")];
    const live = [turn("assistant", "opening")];
    expect(mergeRestoredMessages(history, live)).toEqual(history);
  });

  it("drops a history turn that is still streaming so it is not shown twice", () => {
    const history = [turn("user", "a1"), turn("assistant", "opening line")];
    const live = [turn("user", "a1")];
    expect(mergeRestoredMessages(history, live, "opening")).toEqual([turn("user", "a1")]);
  });
});
