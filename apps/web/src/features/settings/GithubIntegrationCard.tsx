/**
 * @file GithubIntegrationCard.tsx
 * @description Third-party integration card: link a real GitHub account via a
 * fine-grained personal access token so agents share the authenticated quota
 * (5,000 req/h) instead of the anonymous one (60 req/h). The token is pasted
 * once, AES-encrypted server-side, and never read back — the UI only shows a
 * tail mask plus live quota from the Test probe.
 */

"use client";

import { useEffect, useState } from "react";
import { Github, PlugZap } from "lucide-react";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { formatApiError } from "@/lib/api/base";
import { settingsHttp } from "@/lib/api/clients";

export function GithubIntegrationCard() {
  const t = useT("settings");
  const [configured, setConfigured] = useState(false);
  const [tail, setTail] = useState("");
  const [draft, setDraft] = useState("");
  const [quota, setQuota] = useState<{ remaining?: number; limit?: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [clearing, setClearing] = useState(false);

  const refresh = async () => {
    try {
      const status = await settingsHttp.githubStatus();
      setConfigured(status.configured);
      setTail(status.tail ?? "");
    } catch {
      // Keep the previous display; the page-level loader owns hard failures.
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const fail = (err: unknown, fallbackKey: "integrations.github.saveFailed" | "integrations.github.testFailed") => {
    toast.error(err instanceof Error ? formatApiError(err) : t(fallbackKey));
  };

  const handleSaveTest = async () => {
    const token = draft.trim();
    if (!token) return;
    setSaving(true);
    try {
      const saved = await settingsHttp.saveGithubToken(token);
      setConfigured(saved.configured);
      setTail(saved.tail ?? "");
      setDraft("");
      toast.success(t("integrations.github.saved"));
      await handleTest();
    } catch (err) {
      fail(err, "integrations.github.saveFailed");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await settingsHttp.testGithubToken();
      if (result.ok) {
        setQuota({ remaining: result.remaining, limit: result.limit });
        toast.success(t("integrations.github.testPassed"));
      } else {
        setQuota(null);
        toast.error(result.message || t("integrations.github.testFailed"));
      }
    } catch (err) {
      setQuota(null);
      fail(err, "integrations.github.testFailed");
    } finally {
      setTesting(false);
    }
  };

  const handleClear = async () => {
    setClearing(true);
    try {
      await settingsHttp.clearGithubToken();
      setConfigured(false);
      setTail("");
      setQuota(null);
      toast.success(t("integrations.github.cleared"));
    } catch (err) {
      fail(err, "integrations.github.saveFailed");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Github size={16} className="text-[var(--primary)]" />
        <h2 className="text-[14px] font-semibold">{t("integrations.github.title")}</h2>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-muted">{t("integrations.github.desc")}</p>
      <p className="mt-1 text-[12px] text-ink-subtle">
        {configured
          ? t("integrations.github.configured", { tail })
          : t("integrations.github.unconfigured")}
        {quota?.remaining !== undefined
          ? ` · ${t("integrations.github.quota", { remaining: quota.remaining, limit: quota.limit ?? "?" })}`
          : null}
      </p>
      <div className="mt-3 flex max-w-md flex-col gap-2">
        <input
          type="password"
          className="input text-[13px]"
          autoComplete="off"
          spellCheck={false}
          placeholder={t("integrations.github.placeholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary text-[13px]"
            disabled={saving || testing || !draft.trim()}
            onClick={() => void handleSaveTest()}
          >
            {t("integrations.github.saveAndTest")}
          </button>
          <button
            type="button"
            className="btn-secondary text-[13px]"
            disabled={saving || testing}
            onClick={() => void handleTest()}
          >
            <PlugZap size={13} className="mr-1 inline" />
            {t("integrations.github.test")}
          </button>
          {configured ? (
            <button
              type="button"
              className="btn-secondary text-[13px]"
              disabled={clearing || saving}
              onClick={() => void handleClear()}
            >
              {t("integrations.github.clear")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
