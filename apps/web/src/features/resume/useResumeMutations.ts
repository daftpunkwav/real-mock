/**
 * @file useResumeMutations
 * @description Persist resume upload / activate / delete; streaming analysis
 * lives in useAnalyzeStream and is re-exposed here so the page API is stable.
 *
 * Responsibilities:
 * - Upload with input-reset and toast (version-cap gate shared via canAddVersion)
 * - Activate / delete then silently reload the collection
 * - On reload failure, toast listRefreshFailed only (write already succeeded)
 *
 * Must not own list loading; may set preview to the newly uploaded version
 * only. Dialogs stay on list items.
 */

"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { formatApiError } from "@/lib/api/base";
import { resumeHttp as api } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { getTranslator } from "@/i18n/resolve";
import { MAX_RESUME_VERSIONS } from "./resumeLimits";
import type { ResumeItem } from "./resumeNormalize";
import { validateResumeFile } from "./resumeUploadValidation";
import { useAnalyzeStream } from "./useAnalyzeStream";
import { canAddVersion, familyIdOf } from "./versionCompare";

interface ResumeMutationsDeps {
  resumes: ResumeItem[];
  load: (options?: { silent?: boolean }) => Promise<unknown>;
  setPreviewId: (id: number) => void;
}

function toUserMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? formatApiError(err) : fallback;
}

export function useResumeMutations({ resumes, load, setPreviewId }: ResumeMutationsDeps) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const analyze = useAnalyzeStream({ resumes, load, setPreviewId });

  const refreshAfterMutation = () => load({ silent: true });

  const toastSaved = async (message: string) => {
    try {
      await refreshAfterMutation();
      toast.success(message);
    } catch {
      toast.error(getTranslator("resume")("toast.listRefreshFailed"));
    }
  };

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const t = getTranslator("resume");
    try {
      validateResumeFile(file);
    } catch (err) {
      setUploadError(toUserMessage(err, t("toast.uploadFailed")));
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setUploading(true);
    setUploadError("");
    try {
      const uploaded = await api.uploadResume(file);
      // Parsing is asynchronous: the row lands as pending and the poller in
      // useResumeCollection reports the settled (degraded/failed) state.
      await toastSaved(t("toast.uploadQueued"));
      if (uploaded.parse_status === "pending") setPreviewId(uploaded.id);
    } catch (err) {
      setUploadError(toUserMessage(err, t("toast.uploadFailed")));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleUploadVersion = async (anchorId: number, file: File) => {
    const t = getTranslator("resume");
    try {
      validateResumeFile(file);
    } catch (err) {
      setUploadError(toUserMessage(err, t("toast.uploadFailed")));
      return;
    }
    const anchor = resumes.find((row) => row.id === anchorId);
    const familyId = familyIdOf(anchor ?? { id: anchorId });
    const familySize = resumes.filter((row) => familyIdOf(row) === familyId).length;
    if (!canAddVersion(familySize, MAX_RESUME_VERSIONS)) {
      toast.error(t("toast.versionCap", { count: MAX_RESUME_VERSIONS }));
      return;
    }
    setUploading(true);
    setUploadError("");
    try {
      const uploaded = await api.uploadVersion(anchorId, file);
      setPreviewId(uploaded.id);
      await toastSaved(t("toast.uploadQueued"));
    } catch (err) {
      setUploadError(toUserMessage(err, t("toast.uploadFailed")));
    } finally {
      setUploading(false);
    }
  };

  const handleRetryParse = async (id: number) => {
    const t = getTranslator("resume");
    try {
      await api.retryResumeParse(id);
      await refreshAfterMutation();
    } catch (err) {
      toast.error(toUserMessage(err, t("toast.parseRetryFailed")));
    }
  };

  const handleActivate = async (id: number) => {
    const t = getTranslator("resume");
    try {
      await api.activateResume(id);
      await toastSaved(t("toast.activated"));
    } catch (err) {
      toast.error(toUserMessage(err, t("toast.activateFailed")));
    }
  };

  const handleDelete = async (id: number) => {
    const t = getTranslator("resume");
    try {
      await api.deleteResume(id);
      await toastSaved(t("toast.deleted"));
    } catch (err) {
      toast.error(toUserMessage(err, t("toast.deleteFailed")));
    }
  };

  return {
    uploading,
    analyzingIds: analyze.analyzingIds,
    analyzeProgressById: analyze.analyzeProgressById,
    uploadError,
    analyzeError: analyze.analyzeError,
    inputRef,
    handleUpload,
    handleUploadVersion,
    handleAnalyze: analyze.handleAnalyze,
    handleActivate,
    handleDelete,
    handleRetryParse,
  };
}
