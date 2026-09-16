import type { Icon } from "@phosphor-icons/react";

export function MetricCard({ label, value, icon: IconComponent, tone = "neutral" }: { label: string; value: number; icon: Icon; tone?: "neutral" | "live" | "success" | "warning" | "danger" }) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <span className="metric-card__icon"><IconComponent size={18} weight="bold" aria-hidden="true" /></span>
      <div><span>{label}</span><strong dir="ltr">{value.toLocaleString("fa-IR")}</strong></div>
    </article>
  );
}
