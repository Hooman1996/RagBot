import { WarningCircle, Tray } from "@phosphor-icons/react";
import type { PropsWithChildren, ReactNode } from "react";
import { Button } from "./Button";

export function SkeletonRows({ count = 4 }: { count?: number }) {
  return <div className="skeleton-list" aria-label="در حال بارگذاری">{Array.from({ length: count }, (_, index) => <div className="skeleton" key={index} />)}</div>;
}

export function EmptyState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return <div className="empty-state"><Tray size={32} /><h3>{title}</h3><p>{message}</p>{action}</div>;
}

export function ErrorState({ title = "دریافت اطلاعات انجام نشد", error, retry }: { title?: string; error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : "خطای ناشناخته";
  return <div className="error-state" role="alert"><WarningCircle size={24} /><div><strong>{title}</strong><p dir="ltr">{message}</p></div>{retry && <Button variant="secondary" onClick={retry}>تلاش دوباره</Button>}</div>;
}

export function Definition({ label, children, ltr = false }: PropsWithChildren<{ label: string; ltr?: boolean }>) {
  return <div className="definition"><dt>{label}</dt><dd dir={ltr ? "ltr" : "auto"}>{children || "-"}</dd></div>;
}
