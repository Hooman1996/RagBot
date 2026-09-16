import { ServiceStatusBar } from "../ServiceStatusBar";

export function Topbar({ title, englishTitle }: { title: string; englishTitle: string }) {
  return (
    <header className="global-topbar">
      <div className="topbar-title">
        <span>RagBot Evaluation</span>
        <strong>{title}</strong>
        <small dir="ltr">{englishTitle}</small>
      </div>
      <ServiceStatusBar />
    </header>
  );
}
