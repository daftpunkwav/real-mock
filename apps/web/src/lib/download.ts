/**
 * @file download.ts
 * @description Shared file-download helper: save text as a UTF-8 file via a
 * transient object URL. Single implementation reused by every component that
 * offers an export action.
 */

/** Download text as a file with the given filename and MIME type. */
export function downloadTextFile(filename: string, text: string, mime = "text/markdown;charset=utf-8"): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
