/** Strip punctuation/whitespace for echo-similarity checks. */
export function normalizeEchoText(s: string): string {
  return s
    .replace(
      /[\s*#`~\uFF0C\u3002\uFF01\uFF1F\u3001,.!?;:\uFF1A\uFF1B""''\-—…\uFF08\uFF09()\u3010\u3011\[\]]/g,
      "",
    )
    .toLowerCase();
}

/** Whether candidate text closely matches the previous interviewer line (likely speaker echo). */
export function isLikelyEchoOfAssistant(userText: string, assistantText: string): boolean {
  const u = normalizeEchoText(userText);
  const a = normalizeEchoText(assistantText);
  if (u.length < 12 || a.length < 12) return false;
  if (u.includes(a.slice(0, Math.min(40, a.length))) || a.includes(u.slice(0, Math.min(40, u.length)))) {
    return true;
  }
  const window = Math.min(u.length, a.length, 80);
  let hit = 0;
  for (let i = 0; i < window; i++) {
    if (u[i] === a[i]) hit += 1;
  }
  if (hit / window >= 0.55) return true;
  const probe = u.slice(0, Math.min(24, u.length));
  if (probe.length >= 12 && a.includes(probe)) return true;
  return false;
}
