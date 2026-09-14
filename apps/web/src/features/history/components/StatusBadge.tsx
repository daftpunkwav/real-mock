import { CheckCircle2, Circle, Clock } from "lucide-react";
import { useT } from "@/i18n";

/** Session status logo: completed "completed" / active "in progress" / pending "to be started". */
export function StatusBadge({ status }: { status: string }) {
  const t = useT("history");
  const config = {
    completed: { icon: CheckCircle2, textKey: "status.completed", className: "chip-green" },
    active: { icon: Clock, textKey: "status.active", className: "chip-blue" },
    pending: { icon: Circle, textKey: "status.pending", className: "chip-gray" },
  } as const;
  const c = config[status as keyof typeof config] || config.pending;
  const Icon = c.icon;
  return (
    <span className={`chip ${c.className}`}>
      <Icon size={11} />
      {t(c.textKey)}
    </span>
  );
}
