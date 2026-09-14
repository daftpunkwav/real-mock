/**
 * @file clipboard.ts
 * @description Shared clipboard helper: async Clipboard API with a textarea
 * fallback for non-secure contexts. Single implementation reused by every
 * component that offers a copy action.
 */

/** Copy text to the clipboard; resolves false when unavailable or denied. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Non-secure contexts (plain http) lack the async clipboard API.
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(area);
      return ok;
    } catch {
      return false;
    }
  }
}
