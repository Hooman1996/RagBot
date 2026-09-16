import type { PropsWithChildren } from "react";
import type { PanelName } from "../../hooks/useUrlState";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const titles: Record<PanelName, { fa: string; en: string }> = {
  overview: { fa: "نمای کلی", en: "Overview" },
  datasets: { fa: "مجموعه داده‌ها", en: "Datasets" },
  runs: { fa: "اجراها", en: "Runs" },
  stability: { fa: "پایداری", en: "Stability" },
  pipeline: { fa: "خط لوله", en: "Pipeline" },
  system: { fa: "سیستم", en: "System" },
};

export function AppShell({ panel, onNavigate, children }: PropsWithChildren<{ panel: PanelName; onNavigate: (panel: PanelName) => void }>) {
  return (
    <div className="app-shell">
      <Sidebar panel={panel} onNavigate={onNavigate} />
      <div className="app-frame">
        <Topbar title={titles[panel].fa} englishTitle={titles[panel].en} />
        <main className="workspace" id="main-content">{children}</main>
      </div>
    </div>
  );
}
