import {
  BarChart3,
  BookOpen,
  Building2,
  FileText,
  KeyRound,
  MessageSquare,
  Mic,
  Shield,
  Sparkles,
  Video,
} from "lucide-react";

// The display copy adopts i18n in a unified way: the field stores the message key (home namespace), and t() is used to retrieve the word when rendering the component.
export const STEPS = [
  {
    n: "01",
    titleKey: "steps.items.key.title",
    descKey: "steps.items.key.desc",
    href: "/settings",
    icon: KeyRound,
  },
  {
    n: "02",
    titleKey: "steps.items.resume.title",
    descKey: "steps.items.resume.desc",
    href: "/resume",
    icon: FileText,
  },
  {
    n: "03",
    titleKey: "steps.items.interview.title",
    descKey: "steps.items.interview.desc",
    href: "/interview",
    icon: Mic,
  },
];

export const FEATURES = [
  {
    icon: Sparkles,
    titleKey: "features.items.dynamic.title",
    descKey: "features.items.dynamic.desc",
    tint: "brand",
  },
  {
    icon: MessageSquare,
    titleKey: "features.items.probe.title",
    descKey: "features.items.probe.desc",
    tint: "green",
  },
  {
    icon: Building2,
    titleKey: "features.items.company.title",
    descKey: "features.items.company.desc",
    tint: "warning",
  },
  {
    icon: Video,
    titleKey: "features.items.av.title",
    descKey: "features.items.av.desc",
    tint: "danger",
  },
  {
    icon: BookOpen,
    titleKey: "features.items.prep.title",
    descKey: "features.items.prep.desc",
    tint: "brand",
  },
  {
    icon: BarChart3,
    titleKey: "features.items.report.title",
    descKey: "features.items.report.desc",
    tint: "green",
  },
] as const;

export const TRUST_POINTS = [
  {
    icon: Shield,
    tint: "icon-badge-success",
    titleKey: "trust.items.local.title",
    descKey: "trust.items.local.desc",
  },
  {
    icon: KeyRound,
    tint: "icon-badge-brand",
    titleKey: "trust.items.byok.title",
    descKey: "trust.items.byok.desc",
  },
  {
    icon: Sparkles,
    tint: "icon-badge-warning",
    titleKey: "trust.items.opensource.title",
    descKey: "trust.items.opensource.desc",
  },
];
