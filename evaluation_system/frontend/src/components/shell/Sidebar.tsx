import {
  ChartDonut, Database, GearSix, GitBranch, House, Pulse, Waveform,
  type Icon,
} from "@phosphor-icons/react";
import type { PanelName } from "../../hooks/useUrlState";

interface NavigationItem {
  panel: PanelName;
  label: string;
  english: string;
  icon: Icon;
  enabled: boolean;
}

const navigation: NavigationItem[] = [
  { panel: "overview", label: "نمای کلی", english: "Overview", icon: House, enabled: true },
  { panel: "datasets", label: "مجموعه داده‌ها", english: "Datasets", icon: Database, enabled: true },
  { panel: "runs", label: "اجراها", english: "Runs", icon: ChartDonut, enabled: true },
  { panel: "stability", label: "پایداری", english: "Stability", icon: Pulse, enabled: true },
  { panel: "pipeline", label: "خط لوله", english: "Pipeline", icon: GitBranch, enabled: true },
  { panel: "system", label: "سیستم", english: "System", icon: GearSix, enabled: false },
];

export function Sidebar({ panel, onNavigate }: { panel: PanelName; onNavigate: (panel: PanelName) => void }) {
  return (
    <aside className="sidebar">
      <button className="sidebar-brand" type="button" onClick={() => onNavigate("overview")} aria-label="RagBot Evaluation - نمای کلی">
        <span className="sidebar-brand__mark"><Waveform size={22} weight="bold" aria-hidden="true" /></span>
        <span><strong>RagBot</strong><small>Evaluation Console</small></span>
      </button>
      <nav className="sidebar-nav" aria-label="ناوبری اصلی ارزیابی">
        {navigation.map((item) => {
          const IconComponent = item.icon;
          const active = item.panel === panel;
          return (
            <button
              key={item.panel}
              type="button"
              className={active ? "is-active" : ""}
              disabled={!item.enabled}
              aria-current={active ? "page" : undefined}
              aria-label={item.enabled ? item.label : `${item.label}، در حال مهاجرت`}
              title={item.enabled ? item.english : `${item.english} - در حال مهاجرت`}
              onClick={() => onNavigate(item.panel)}
            >
              <IconComponent size={20} weight={active ? "fill" : "regular"} aria-hidden="true" />
              <span><strong>{item.label}</strong><small>{item.enabled ? item.english : "در حال مهاجرت"}</small></span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <span>فضای ارزیابی فنی</span>
        <small>Gateway protected</small>
      </div>
    </aside>
  );
}
