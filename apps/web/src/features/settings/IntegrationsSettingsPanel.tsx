/** Integrations settings tab: third-party account linking cards (GitHub, future providers). */

"use client";

import { GithubIntegrationCard } from "@/features/settings/GithubIntegrationCard";

export function IntegrationsSettingsPanel() {
  return (
    <div className="min-w-0 space-y-4">
      <GithubIntegrationCard />
    </div>
  );
}
