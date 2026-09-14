import { beforeEach, describe, expect, it } from "vitest";

import {
  clearArchive,
  loadArchive,
  pushArchivedGroup,
  toArchivedCopy,
} from "../compactionArchive";
import type { PrepChatMessage } from "@/features/prep/types";

function installMemoryStorage() {
  const store = new Map<string, string>();
  (globalThis as Record<string, unknown>).window = {
    localStorage: {
      getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
    },
  };
  return store;
}

function msg(id: string, role: "user" | "assistant", backendIndex: number): PrepChatMessage {
  return { id, role, content: `${id}-body`, backendIndex };
}

describe("compactionArchive", () => {
  beforeEach(() => {
    installMemoryStorage();
  });

  it("returns null when nothing is stored", () => {
    expect(loadArchive(7)).toBeNull();
  });

  it("pushes a group and restores it with prefixed ids", () => {
    const next = pushArchivedGroup(7, {
      version: 1,
      forkPoint: 8,
      backupSessionId: 42,
      staleBackup: false,
      messages: [msg("u-1", "user", 0), msg("a-2", "assistant", 1)],
    });
    expect(next.groups).toHaveLength(1);
    expect(next.groups[0]?.staleBackup).toBe(false);
    const loaded = loadArchive(7);
    expect(loaded?.groups[0]?.messages.map((m) => m.id)).toEqual([
      "archived-u-1",
      "archived-a-2",
    ]);
    expect(loaded?.groups[0]?.messages[0]?.backendIndex).toBe(0);
  });

  it("marks older groups stale on the next push", () => {
    pushArchivedGroup(7, {
      version: 1,
      forkPoint: 8,
      backupSessionId: 42,
      staleBackup: false,
      messages: [msg("u-1", "user", 0)],
    });
    const next = pushArchivedGroup(7, {
      version: 2,
      forkPoint: 12,
      backupSessionId: 43,
      staleBackup: false,
      messages: [msg("u-9", "user", 9)],
    });
    expect(next.groups.map((g) => g.staleBackup)).toEqual([true, false]);
  });

  it("survives garbage and clears cleanly", () => {
    window.localStorage.setItem("realmock_prep_archive_7", "not-json{{{");
    expect(loadArchive(7)).toBeNull();
    pushArchivedGroup(7, {
      version: 1,
      forkPoint: 1,
      backupSessionId: null,
      staleBackup: false,
      messages: [msg("u-1", "user", 0)],
    });
    clearArchive(7);
    expect(loadArchive(7)).toBeNull();
  });

  it("strips live-only fields from copies", () => {
    const copy = toArchivedCopy({
      id: "a-1",
      role: "assistant",
      content: "hi",
      streaming: true,
      statusText: "thinking",
      backendIndex: 4,
    });
    expect(copy).toMatchObject({ id: "archived-a-1", backendIndex: 4 });
    expect(copy).not.toHaveProperty("streaming");
    expect(copy).not.toHaveProperty("statusText");
  });
});
