import { CaretLeft, Funnel, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { PageHeader } from "../../components/shell/PageHeader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatDate, formatDuration, shortHash } from "../../components/ui/format";

const ACTIVE = new Set(["PENDING", "RUNNING"]);

function elapsed(start: string | null, finish: string | null) {
  if (!start) return "شروع نشده";
  const end = finish ? Date.parse(finish) : Date.now();
  return formatDuration(Math.max(0, end - Date.parse(start)));
}

export function RunsIndex({ onOpen }: { onOpen: (id: string) => void }) {
  const api = useEvaluationApi();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const [status, setStatus] = useState("ALL");
  const [type, setType] = useState("ALL");
  const [dataset, setDataset] = useState("ALL");
  const [errors, setErrors] = useState(false);
  const [fallbacks, setFallbacks] = useState(false);
  const datasetNames = useMemo(() => new Map((datasets.data || []).map((item) => [item.id, item.filename || item.id])), [datasets.data]);
  const rows = useMemo(() => [...(runs.data || [])]
    .filter((run) => status === "ALL" || run.status === status)
    .filter((run) => type === "ALL" || run.run_type === type)
    .filter((run) => dataset === "ALL" || run.dataset_id === dataset)
    .filter((run) => !errors || run.error_count > 0 || run.infrastructure_error_count > 0)
    .filter((run) => !fallbacks || run.fallback_count > 0)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), [dataset, errors, fallbacks, runs.data, status, type]);

  return <main className="runs-page">
    <PageHeader title="اجراها" description="نمای عملیاتی همه اجراهای ارزیابی و وضعیت ماندگار آن‌ها در PostgreSQL." />
    <section className="surface runs-index" aria-label="فهرست اجراها">
      <div className="runs-filters">
        <Funnel size={18} />
        <label><span>وضعیت</span><select aria-label="فیلتر وضعیت اجرا" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">همه</option>{["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>نوع اجرا</span><select aria-label="فیلتر نوع اجرا" value={type} onChange={(event) => setType(event.target.value)}><option value="ALL">همه</option>{["DATASET_INSPECTION", "STABILITY_QUERY", "STABILITY_SESSION", "STABILITY_DATASET"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>مجموعه داده</span><select aria-label="فیلتر مجموعه داده" value={dataset} onChange={(event) => setDataset(event.target.value)}><option value="ALL">همه</option>{(datasets.data || []).map((item) => <option key={item.id} value={item.id}>{item.filename || item.id}</option>)}</select></label>
        <label className="check-filter"><input type="checkbox" checked={errors} onChange={(event) => setErrors(event.target.checked)} />دارای خطا</label>
        <label className="check-filter"><input type="checkbox" checked={fallbacks} onChange={(event) => setFallbacks(event.target.checked)} />دارای Fallback</label>
      </div>
      {runs.isLoading || datasets.isLoading ? <div className="runs-loading"><SkeletonRows count={8} /></div> : runs.isError || datasets.isError ? <ErrorState title="فهرست اجراها قابل دریافت نیست" error={runs.error || datasets.error} retry={() => { void runs.refetch(); void datasets.refetch(); }} /> : !rows.length ? <EmptyState title="اجرایی مطابق فیلترها نیست" message="فیلترها را تغییر دهید یا یک اجرای ارزیابی تازه ایجاد کنید." /> : <div className="table-wrap"><table className="data-table runs-table">
        <thead><tr><th>Run ID</th><th>Dataset</th><th>Run Type</th><th>Status</th><th>Progress</th><th>Sessions</th><th>Turns</th><th>Fallbacks</th><th>Errors</th><th>Infra</th><th>Duration</th><th>Git SHA</th><th>Created / Started</th><th></th></tr></thead>
        <tbody>{rows.map((run) => <tr key={run.id} className={ACTIVE.has(run.status) ? "is-active" : ""}>
          <td><button className="technical-link" dir="ltr" title={run.id} onClick={() => onOpen(run.id)}>{run.id}</button></td>
          <td title={run.dataset_id || ""}>{run.dataset_id ? datasetNames.get(run.dataset_id) || shortHash(run.dataset_id) : "-"}</td>
          <td><code dir="ltr">{run.run_type}</code></td><td><StatusBadge status={run.status} /></td>
          <td><span className="run-progress-number" dir="ltr">{run.total_turns ? Math.round(run.completed_turns / run.total_turns * 100) : 0}%</span></td>
          <td dir="ltr">{run.completed_sessions} / {run.total_sessions}</td><td dir="ltr">{run.completed_turns} / {run.total_turns}</td>
          <td className={run.fallback_count ? "count-warning" : ""}>{run.fallback_count}</td><td className={run.error_count ? "count-danger" : ""}>{run.error_count}</td><td className={run.infrastructure_error_count ? "count-danger" : ""}>{run.infrastructure_error_count}</td>
          <td dir="ltr">{elapsed(run.started_at, run.finished_at)}</td><td><code dir="ltr" title={run.git_commit_sha || ""}>{shortHash(run.git_commit_sha)}</code></td>
          <td><time dateTime={run.created_at}>{formatDate(run.created_at)}</time>{run.started_at && <small>{formatDate(run.started_at)}</small>}</td>
          <td><button className="icon-button" aria-label={`باز کردن اجرای ${run.id}`} onClick={() => onOpen(run.id)}><CaretLeft /></button></td>
        </tr>)}</tbody>
      </table></div>}
      {runs.data && !rows.length && (errors || fallbacks) && <p className="runs-filter-note"><WarningCircle />هیچ اجرا با این شرایط ثبت نشده است.</p>}
    </section>
  </main>;
}
