"use client";

/**
 * @file ResumeUploadArea.tsx
 * @description Dashed upload control for a single resume file.
 *
 * Responsibilities:
 * - Trigger the hidden file input and show parse/error states
 *
 * Accept string comes from resumeLimits (aligned with the API catalog).
 */

import type { ChangeEvent, RefObject } from "react";
import { Upload } from "lucide-react";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import { RESUME_ACCEPT } from "../resumeLimits";

interface ResumeUploadAreaProps {
  uploading: boolean;
  error: string;
  inputRef: RefObject<HTMLInputElement | null>;
  onUpload: (e: ChangeEvent<HTMLInputElement>) => void;
}

export function ResumeUploadArea({ uploading, error, inputRef, onUpload }: ResumeUploadAreaProps) {
  const t = useT("resume");
  return (
    <>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="group surface-card flex w-full cursor-pointer flex-col items-center justify-center border-dashed !border-2 p-6 text-center hover:border-[var(--primary)] hover:bg-[var(--info-soft)] sm:p-8 disabled:opacity-60"
      >
        {uploading ? (
          <Spinner className="h-7 w-7" color="primary" />
        ) : (
          <span className="icon-badge icon-badge-brand transition-transform group-hover:scale-105">
            <Upload size={16} strokeWidth={1.75} />
          </span>
        )}
        <p className="mt-3 text-[13px] font-medium text-ink">
          {uploading ? t("upload.parsing") : t("upload.cta")}
        </p>
        <p className="mt-1 text-[11px] text-ink-subtle">{t("upload.formats")}</p>
        <input
          ref={inputRef}
          type="file"
          accept={RESUME_ACCEPT}
          className="hidden"
          onChange={onUpload}
        />
      </button>

      {error && <div className="alert alert-error">{error}</div>}
    </>
  );
}
