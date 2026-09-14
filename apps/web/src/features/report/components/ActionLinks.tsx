"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useT } from "@/i18n";

/** " "" ". */
export function ActionLinks() {
  const t = useT("report");
  return (
    <div className="mt-7 flex flex-wrap gap-2.5">
      <Link href="/interview" className="btn-primary">
        <RefreshCw size={13} /> {t("actions.again")}
      </Link>
      <Link href="/growth" className="btn-secondary">
        {t("actions.growth")}
      </Link>
    </div>
  );
}
