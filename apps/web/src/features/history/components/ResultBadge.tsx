/** Round + verdict badges shared by history list and detail views. */

import { useT } from "@/i18n";

/** Round-N chip; renders nothing for standalone sessions. */
export function RoundBadge({ roundNo }: { roundNo?: number | null }) {
  const t = useT("history");
  if (!roundNo) return null;
  return <span className="chip chip-blue shrink-0">{t("list.round", { n: roundNo })}</span>;
}

/** Verdict chip: passed (green) / failed (red) / unjudged (gray). */
export function ResultBadge({ result }: { result?: string | null }) {
  const t = useT("history");
  if (result === "passed") {
    return <span className="chip chip-green shrink-0">{t("result.passed")}</span>;
  }
  if (result === "failed") {
    return <span className="chip chip-red shrink-0">{t("result.failed")}</span>;
  }
  return null;
}
