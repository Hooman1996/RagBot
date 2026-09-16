import { Copy, Play, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { useEffect } from "react";
import type { Dataset, DatasetSession, DatasetTurn } from "../../types/api";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatDate, shortHash } from "../../components/ui/format";
import { DatasetSessions } from "./DatasetSessions";
import { DatasetTurns } from "./DatasetTurns";

export function DatasetDetails({ dataset, sessions, sessionsLoading, sessionsError, selectedSessionId, turns, turnsLoading, turnsError, onSessionSelect, onSessionsRetry, onTurnsRetry, onRunRequest }: {
  dataset: Dataset;
  sessions: DatasetSession[];
  sessionsLoading: boolean;
  sessionsError: unknown;
  selectedSessionId: string | null;
  turns: DatasetTurn[];
  turnsLoading: boolean;
  turnsError: unknown;
  onSessionSelect: (id: string) => void;
  onSessionsRetry: () => void;
  onTurnsRetry: () => void;
  onRunRequest: () => void;
}) {
  const selectedSession = sessions.find((item) => item.id === selectedSessionId) || null;
  useEffect(() => {
    if (sessions.length && (!selectedSessionId || !sessions.some((item) => item.id === selectedSessionId))) onSessionSelect(sessions[0].id);
  }, [onSessionSelect, selectedSessionId, sessions]);

  return <main className="dataset-details">
    <section className="dataset-summary surface" aria-labelledby="dataset-summary-title">
      <div className="dataset-summary__head">
        <div>
          <div className="dataset-summary__title-line"><h2 id="dataset-summary-title" dir="auto">{dataset.filename || `مجموعه ${dataset.id.slice(0, 8)}`}</h2><Badge tone={dataset.dataset_type === "PIPELINE_INSPECTION" ? "info" : "neutral"}>{dataset.dataset_type}</Badge></div>
          <div className="dataset-summary__meta"><span>{dataset.source_type}</span><time dateTime={dataset.created_at}>{formatDate(dataset.created_at)}</time><code dir="ltr">{dataset.id}</code></div>
        </div>
        {dataset.dataset_type === "PIPELINE_INSPECTION" ? <Button onClick={onRunRequest} disabled={dataset.valid_row_count === 0}><Play size={17} weight="fill" />شروع ارزیابی</Button> : <p className="stability-guidance">برای اجرای پایداری از بخش پایداری استفاده کنید.</p>}
      </div>
      <dl className="dataset-metrics">
        <div><dt>کل ردیف‌ها</dt><dd>{dataset.row_count.toLocaleString("fa-IR")}</dd></div>
        <div><dt>ردیف معتبر</dt><dd className="is-success">{dataset.valid_row_count.toLocaleString("fa-IR")}</dd></div>
        <div><dt>ردیف نامعتبر</dt><dd className={dataset.invalid_row_count ? "is-warning" : "is-success"}>{dataset.invalid_row_count.toLocaleString("fa-IR")}</dd></div>
        <div><dt>جلسه‌ها</dt><dd>{dataset.session_count.toLocaleString("fa-IR")}</dd></div>
        <div className="dataset-metrics__sha"><dt>SHA256</dt><dd><code dir="ltr" title={dataset.file_sha256 || "-"}>{shortHash(dataset.file_sha256)}</code>{dataset.file_sha256 && <button aria-label="کپی SHA256" title="کپی SHA256" onClick={() => void navigator.clipboard?.writeText(dataset.file_sha256!)}><Copy size={14} /></button>}</dd></div>
      </dl>
      <div className={`dataset-quality ${dataset.invalid_row_count ? "is-warning" : "is-clean"}`}>
        {dataset.invalid_row_count ? <WarningCircle size={17} /> : <ShieldCheck size={17} />}
        <span>{dataset.invalid_row_count ? `${dataset.invalid_row_count.toLocaleString("fa-IR")} ردیف نامعتبر در این مجموعه ثبت شده است.` : "همه ردیف‌های ثبت‌شده معتبر هستند."}</span>
      </div>
    </section>

    {sessionsLoading ? <section className="surface dataset-loading"><SkeletonRows count={6} /></section> : sessionsError ? <ErrorState title="جلسه‌های مجموعه قابل دریافت نیستند" error={sessionsError} retry={onSessionsRetry} /> : !sessions.length ? <EmptyState title="جلسه‌ای در این مجموعه نیست" message="این مجموعه داده جلسه قابل بازرسی ندارد." /> : <div className="dataset-inspection-grid">
      <DatasetSessions sessions={sessions} selectedId={selectedSessionId} onSelect={onSessionSelect} />
      {selectedSession && (turnsLoading ? <section className="surface dataset-loading"><SkeletonRows count={4} /></section> : turnsError ? <ErrorState title="نوبت‌های جلسه قابل دریافت نیستند" error={turnsError} retry={onTurnsRetry} /> : <DatasetTurns session={selectedSession} turns={turns} />)}
    </div>}
  </main>;
}
