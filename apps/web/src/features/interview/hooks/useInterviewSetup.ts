"use client";

/** Interview setup data domain: options/resumes/model buckets + config + create session. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getTranslator } from "@/i18n/resolve";
import { interviewHttp as api, settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";
import type { ModelProfile, ReasoningEffort, ReferenceDetail, TaskBindings } from "@/types";
import {
  CUSTOM_ROLE_ID,
  isPresetCompany,
  isPresetRole,
  resolveConfigLabelsForApi,
} from "../setup/optionLabels";
import {
  readSetupPrefs,
  restoreModelId,
  restoreSetupConfig,
  writeSetupPrefs,
} from "../setup/prefs";

const DEFAULT_CONFIG: InterviewConfig = {
  role: "backend_engineer",
  level: "mid_engineer",
  company: "bytedance",
  workflow_type: "technical",
  personality: "professional",
  strictness: 3,
  interview_style: "deep_dive",
  resume_id: null,
  avatar_id: "professional_male",
  scene_id: "meeting_room",
  reference_detail: "outline",
};

export function useInterviewSetup() {
  const router = useRouter();
  const [options, setOptions] = useState<Options | null>(null);
  const [resumes, setResumes] = useState<ResumePickerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [creating, setCreating] = useState(false);
  const [config, setConfig] = useState<InterviewConfig>(DEFAULT_CONFIG);
  /** Multi-round process mode: create a process (round 1..5) instead of a standalone session. */
  const [multiRound, setMultiRound] = useState(false);

  const [chatModels, setChatModels] = useState<ModelProfile[]>([]);
  const [sttModels, setSttModels] = useState<ModelProfile[]>([]);
  const [ttsModels, setTtsModels] = useState<ModelProfile[]>([]);
  const [chatModelId, setChatModelId] = useState<number | null>(null);
  const [sttModelId, setSttModelId] = useState<number | null>(null);
  const [ttsModelId, setTtsModelId] = useState<number | null>(null);
  const [effort, setEffort] = useState<ReasoningEffort>("medium");
  /** Reference-answer depth: fast outline (default) or tool-grounded full answer. */
  const [referenceDetail, setReferenceDetail] = useState<ReferenceDetail>("outline");
  const [defaultBindings, setDefaultBindings] = useState<TaskBindings | null>(null);

  // Stored preferences are read once; state keeps defaults until the catalogs
  // validate them, so SSR/hydration output stays identical.
  const storedPrefs = useMemo(() => readSetupPrefs(), []);
  /** True once catalog-dependent restores finished; gates preference write-back. */
  const [prefsRestored, setPrefsRestored] = useState(false);
  const restoreGatesRef = useRef(2);
  const markPrefsRestored = () => {
    restoreGatesRef.current -= 1;
    if (restoreGatesRef.current <= 0) setPrefsRestored(true);
  };

  const loadData = () => {
    setLoading(true);
    setLoadError("");
    Promise.all([api.getOptions(), api.listResumes()])
      .then(([opts, res]) => {
        setOptions(opts);
        setResumes(res);
        // Restore last-used choices; a stored resume only wins while it still
        // exists, otherwise the active resume fallback applies.
        const restored = restoreSetupConfig(storedPrefs.config, opts, res);
        setConfig((c) => {
          const next = { ...c, ...restored };
          if (restored.resume_id === undefined && res.length > 0) {
            const active = res.find((r) => r.is_active) ?? res[0];
            if (active) next.resume_id = active.id;
          }
          return next;
        });
        markPrefsRestored();
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : getTranslator("interview")("setup.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  // Storage-only preferences (no catalog validation needed).
  useEffect(() => {
    if (storedPrefs.multiRound !== undefined) setMultiRound(storedPrefs.multiRound);
    if (storedPrefs.effort) setEffort(storedPrefs.effort);
    if (storedPrefs.referenceDetail) setReferenceDetail(storedPrefs.referenceDetail);
  }, [storedPrefs]);

  // Processor buckets by capability; load failure must not block setup
  useEffect(() => {
    settingsHttp
      .listModelOptions()
      .then((res) => {
        const list = Array.isArray(res?.models) ? res.models : [];
        const chat = list.filter((m) => m.capabilities?.chat);
        const stt = list.filter((m) => m.capabilities?.audio_input);
        const tts = list.filter((m) => m.capabilities?.audio_output);
        setChatModels(chat);
        setSttModels(stt);
        setTtsModels(tts);
        setChatModelId(restoreModelId(storedPrefs.chatModelId, chat));
        setSttModelId(restoreModelId(storedPrefs.sttModelId, stt));
        setTtsModelId(restoreModelId(storedPrefs.ttsModelId, tts));
        markPrefsRestored();
      })
      .catch(() => markPrefsRestored());
    settingsHttp.getBindings().then(setDefaultBindings).catch(() => {});
  }, [storedPrefs]);

  // Write-back on every change so the next visit restores the latest choices.
  useEffect(() => {
    if (!prefsRestored) return;
    writeSetupPrefs({ config, multiRound, chatModelId, sttModelId, ttsModelId, effort, referenceDetail });
  }, [prefsRestored, config, multiRound, chatModelId, sttModelId, ttsModelId, effort, referenceDetail]);

  const set = (patch: Partial<InterviewConfig>) => setConfig((c) => ({ ...c, ...patch }));

  const start = async () => {
    const t = getTranslator("interview");
    const roleIds = options?.roles ?? [];
    if (!isPresetRole(config.role, roleIds) && !config.role.trim()) {
      toast.error(t("setup.role.customRequired"));
      return;
    }
    if (config.role === CUSTOM_ROLE_ID) {
      toast.error(t("setup.role.customRequired"));
      return;
    }
    if (!isPresetCompany(config.company, options?.companies ?? []) && !config.company.trim()) {
      toast.error(t("setup.company.customRequired"));
      return;
    }

    setCreating(true);
    try {
      const labels = resolveConfigLabelsForApi(config.role, config.level, roleIds, t);
      const ai = {
        chat_profile_id: chatModelId,
        stt_profile_id: sttModelId,
        tts_profile_id: ttsModelId,
        reasoning_effort: effort,
      };
      if (multiRound) {
        const created = await api.createProcess(
          {
            ...config,
            role: labels.role,
            level: labels.level,
            max_rounds: 5,
            ai_overrides: ai,
          },
          { reference_detail: referenceDetail },
        );
        router.push(`/interview/${created.session_id}`);
        return;
      }
      const session = await api.createSessionWithAI(
        { ...config, role: labels.role, level: labels.level },
        ai,
        { reference_detail: referenceDetail },
      );
      router.push(`/interview/${session.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("setup.createFailed"));
    } finally {
      setCreating(false);
    }
  };

  return {
    options,
    resumes,
    loading,
    loadError,
    creating,
    config,
    multiRound,
    chatModels,
    sttModels,
    ttsModels,
    chatModelId,
    sttModelId,
    ttsModelId,
    effort,
    referenceDetail,
    defaultBindings,
    set,
    setMultiRound,
    setChatModelId,
    setSttModelId,
    setTtsModelId,
    setEffort,
    setReferenceDetail,
    reload: loadData,
    start,
  };
}
