import { CheckCircle, CircleNotch, Clock, Prohibit, WarningCircle } from "@phosphor-icons/react";
import type { RunStatus } from "../../types/api";

const labels: Record<RunStatus, string> = {
  PENDING: "در صف",
  RUNNING: "در حال اجرا",
  COMPLETED: "تکمیل شده",
  FAILED: "ناموفق",
  CANCELLED: "لغو شده",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const IconComponent = status === "COMPLETED" ? CheckCircle : status === "RUNNING" ? CircleNotch : status === "PENDING" ? Clock : status === "CANCELLED" ? Prohibit : WarningCircle;
  return <span className={`status-badge status-badge--${status.toLowerCase()}`}><IconComponent size={13} weight="bold" aria-hidden="true" />{labels[status]}</span>;
}
