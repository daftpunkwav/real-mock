"use client";

import { notFound } from "next/navigation";
import { AvatarStage } from "@/features/avatar";

const CASES = [
  { id: "professional_male", label: "Professional male" },
  { id: "strict_expert", label: "Strict expert" },
  { id: "gentle_female", label: "Gentle female" },
] as const;

/** Side-by-side live AvatarStage check for three portraits (incl. Strict Mode races) */
export default function AvatarDebugPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-bold">Avatar live debug</h1>
      <p className="text-sm text-white/60">
        Expect 3D portraits; a yellow &quot;3D avatar failed to load&quot; bar means it is still broken.
        Hard-refresh with Ctrl+Shift+R and recheck.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {CASES.map((c) => (
          <div key={c.id} className="space-y-2">
            <div className="text-sm font-medium">{c.label}</div>
            <div className="h-[320px] rounded-xl overflow-hidden border border-white/10">
              <AvatarStage avatarId={c.id} sceneId="meeting_room" emotion="neutral" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
