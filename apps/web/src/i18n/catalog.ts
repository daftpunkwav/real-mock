/**
 * Message catalog aggregation: single assembly point for each locale × namespace.
 * zh-CN is the key source; en is forced to the same key set via ``satisfies`` (tests double-check).
 * App code must not import message files directly — use translators from ``@/i18n``.
 */

import { DEFAULT_LOCALE, type LocaleId } from "./locales";
import { common as zhCommon } from "./messages/zh-CN/common";
import { errors as zhErrors } from "./messages/zh-CN/errors";
import { growth as zhGrowth } from "./messages/zh-CN/growth";
import { history as zhHistory } from "./messages/zh-CN/history";
import { home as zhHome } from "./messages/zh-CN/home";
import { interview as zhInterview } from "./messages/zh-CN/interview";
import { media as zhMedia } from "./messages/zh-CN/media";
import { meta as zhMeta } from "./messages/zh-CN/meta";
import { nav as zhNav } from "./messages/zh-CN/nav";
import { prep as zhPrep } from "./messages/zh-CN/prep";
import { profile as zhProfile } from "./messages/zh-CN/profile";
import { report as zhReport } from "./messages/zh-CN/report";
import { resume as zhResume } from "./messages/zh-CN/resume";
import { settings as zhSettings } from "./messages/zh-CN/settings";
import { common as enCommon } from "./messages/en/common";
import { errors as enErrors } from "./messages/en/errors";
import { growth as enGrowth } from "./messages/en/growth";
import { history as enHistory } from "./messages/en/history";
import { home as enHome } from "./messages/en/home";
import { interview as enInterview } from "./messages/en/interview";
import { media as enMedia } from "./messages/en/media";
import { meta as enMeta } from "./messages/en/meta";
import { nav as enNav } from "./messages/en/nav";
import { prep as enPrep } from "./messages/en/prep";
import { profile as enProfile } from "./messages/en/profile";
import { report as enReport } from "./messages/en/report";
import { resume as enResume } from "./messages/en/resume";
import { settings as enSettings } from "./messages/en/settings";

export const NAMESPACE_IDS = [
  "common",
  "nav",
  "home",
  "profile",
  "resume",
  "prep",
  "interview",
  "history",
  "report",
  "growth",
  "settings",
  "media",
  "errors",
  "meta",
] as const;

export type NamespaceId = (typeof NAMESPACE_IDS)[number];

export type MessageTable = Record<string, string>;

export type MessageCatalog = Record<LocaleId, Record<NamespaceId, MessageTable>>;

export const messageCatalog = {
  "zh-CN": {
    common: zhCommon,
    nav: zhNav,
    home: zhHome,
    profile: zhProfile,
    resume: zhResume,
    prep: zhPrep,
    interview: zhInterview,
    history: zhHistory,
    report: zhReport,
    growth: zhGrowth,
    settings: zhSettings,
    media: zhMedia,
    errors: zhErrors,
    meta: zhMeta,
  },
  en: {
    common: enCommon satisfies Record<keyof typeof zhCommon, string>,
    nav: enNav satisfies Record<keyof typeof zhNav, string>,
    home: enHome satisfies Record<keyof typeof zhHome, string>,
    profile: enProfile satisfies Record<keyof typeof zhProfile, string>,
    resume: enResume satisfies Record<keyof typeof zhResume, string>,
    prep: enPrep satisfies Record<keyof typeof zhPrep, string>,
    interview: enInterview satisfies Record<keyof typeof zhInterview, string>,
    history: enHistory satisfies Record<keyof typeof zhHistory, string>,
    report: enReport satisfies Record<keyof typeof zhReport, string>,
    growth: enGrowth satisfies Record<keyof typeof zhGrowth, string>,
    settings: enSettings satisfies Record<keyof typeof zhSettings, string>,
    media: enMedia satisfies Record<keyof typeof zhMedia, string>,
    errors: enErrors satisfies Record<keyof typeof zhErrors, string>,
    meta: enMeta satisfies Record<keyof typeof zhMeta, string>,
  },
} satisfies MessageCatalog;

export type MessagesFor<N extends NamespaceId> = (typeof messageCatalog)["zh-CN"][N];

export type MessageKey<N extends NamespaceId> = Extract<keyof MessagesFor<N>, string>;

export { DEFAULT_LOCALE };
