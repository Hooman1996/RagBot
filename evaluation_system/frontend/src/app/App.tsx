import { Database, Flask, Waveform } from "@phosphor-icons/react";
import { useAuth } from "./auth";
import { AccessGate } from "../components/database-setup/AccessGate";
import { DatabaseGate } from "../components/database-setup/DatabaseGate";
import { useUrlState } from "../hooks/useUrlState";
import { DatasetInspector } from "../features/dataset-inspector/DatasetInspector";
import { StabilityInspector } from "../features/stability-inspector/StabilityInspector";
import { ServiceStatusBar } from "../components/ServiceStatusBar";

export function App() {
  const { authenticated } = useAuth();
  const { panel, runId, update } = useUrlState();
  if (!authenticated) return <AccessGate />;
  return (
    <DatabaseGate>
      <div className="app-shell">
        <header className="topbar">
          <a className="brand" href="?panel=dataset" onClick={(event) => { event.preventDefault(); update({ panel: "dataset", runId: null }); }}>
            <span className="brand__mark"><Waveform size={21} weight="bold" /></span>
            <span><strong>RagBot Evaluation</strong><small>Pipeline observability console</small></span>
          </a>
          <nav className="primary-nav" aria-label="بخش‌های ارزیابی">
            <button className={panel === "dataset" ? "active" : ""} onClick={() => update({ panel: "dataset", runId: null })}><Database size={18} />بازرس داده</button>
            <button className={panel === "stability" ? "active" : ""} onClick={() => update({ panel: "stability", runId: null })}><Flask size={18} />بازرس پایداری</button>
          </nav>
          <span className="auth-context">RagBot account</span>
        </header>
        <ServiceStatusBar />
        <main className="workspace">
          {panel === "dataset" ? <DatasetInspector activeRunId={runId} onRunOpen={(id) => update({ runId: id })} /> : <StabilityInspector activeRunId={runId} onRunOpen={(id) => update({ runId: id })} />}
        </main>
      </div>
    </DatabaseGate>
  );
}
