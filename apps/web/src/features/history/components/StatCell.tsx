/** KPI statistical grid: value + label, which can be emphasized by color. */
export function StatCell({
  value,
  label,
  tone,
}: {
  value: string | number;
  label: string;
  tone?: "success" | "info";
}) {
  const color =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "info"
        ? "text-[var(--primary)]"
        : "text-ink";
  return (
    <div className="kpi-card !p-3">
      <p className={`kpi-value !text-xl ${color}`}>{value}</p>
      <p className="kpi-label mt-1">{label}</p>
    </div>
  );
}
