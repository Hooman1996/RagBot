import type { PropsWithChildren } from "react";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "diverged";

export function Badge({ tone = "neutral", children }: PropsWithChildren<{ tone?: BadgeTone }>) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function statusTone(status: string, infrastructure = false): BadgeTone {
  if (infrastructure || status === "FAILED" || status === "ERROR") return "danger";
  if (status === "COMPLETED" || status === "READY") return "success";
  if (status === "RUNNING") return "info";
  if (status === "CANCELLED" || status === "SKIPPED") return "warning";
  return "neutral";
}
