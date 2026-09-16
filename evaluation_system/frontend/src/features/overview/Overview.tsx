import { ChartDonut, CheckCircle, Clock, Database, PlayCircle, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useEvaluationApi } from "../../api/context";
import { PageHeader } from "../../components/shell/PageHeader";
import { MetricCard } from "../../components/ui/MetricCard";
import { Badge, statusTone } from "../../components/ui/Badge";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatDate } from "../../components/ui/format";
import type { Run, RunStatus } from "../../types/api";

const statusOrder: RunStatus[] = ["COMPLETED", "RUNNING", "PENDING", "FAILED", "CANCELLED"];

export function Overview({ onRunOpen }: { onRunOpen: (run: Run) => void }) {
  const api = useEvaluationApi();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities, staleTime: 30_000 });
  const database = useQuery({ queryKey: ["database-status"], queryFn: api.databaseStatus, staleTime: 30_000 });

  const counts = useMemo(() => {
    const result = { PENDING: 0, RUNNING: 0, COMPLETED: 0, FAILED: 0, CANCELLED: 0 } satisfies Record<RunStatus, number>;
    for (const run of runs.data || []) result[run.status] += 1;
    return result;
  }, [runs.data]);

  const recentRuns = useMemo(
    () => [...(runs.data || [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 6),
    [runs.data],
  );
  const totalRuns = runs.data?.length || 0;
  const fallbackTotal = (runs.data || []).reduce((sum, run) => sum + run.fallback_count, 0);
  const errorTotal = (runs.data || []).reduce((sum, run) => sum + run.error_count, 0);
  const infrastructureErrorTotal = (runs.data || []).reduce((sum, run) => sum + run.infrastructure_error_count, 0);
  const loading = datasets.isLoading || runs.isLoading || capabilities.isLoading || database.isLoading;
  const failedQuery = datasets.isError ? datasets : runs.isError ? runs : capabilities.isError ? capabilities : database.isError ? database : null;

  if (loading) return <div className="overview-page"><PageHeader title="نمای کلی ارزیابی" description="وضعیت جاری داده‌ها و اجرای ارزیابی را از سرویس واقعی مشاهده کنید." /><SkeletonRows count={6} /></div>;
  if (failedQuery) return <div className="overview-page"><PageHeader title="نمای کلی ارزیابی" description="وضعیت جاری داده‌ها و اجرای ارزیابی را از سرویس واقعی مشاهده کنید." /><ErrorState title="داده‌های نمای کلی قابل دریافت نیست" error={failedQuery.error} retry={() => void failedQuery.refetch()} /></div>;

  return (
    <div className="overview-page">
      <PageHeader
        title="نمای کلی ارزیابی"
        description="نمای فشرده‌ای از مجموعه داده‌ها، صف اجرا و آخرین فعالیت‌های سامانه."
        meta={<span className={`capability-state ${capabilities.data!.background_execution_available ? "is-ready" : "is-unavailable"}`}><PlayCircle size={16} weight="fill" />{capabilities.data!.background_execution_available ? "اجرای پس‌زمینه فعال" : "اجرای پس‌زمینه غیرفعال"}</span>}
      />

      <section className="overview-metrics" aria-label="شاخص‌های ارزیابی">
        <MetricCard label="مجموعه داده‌ها" value={datasets.data!.length} icon={Database} />
        <MetricCard label="کل اجراها" value={totalRuns} icon={ChartDonut} />
        <MetricCard label="در صف" value={counts.PENDING} icon={Clock} tone="warning" />
        <MetricCard label="در حال اجرا" value={counts.RUNNING} icon={PlayCircle} tone="live" />
        <MetricCard label="تکمیل شده" value={counts.COMPLETED} icon={CheckCircle} tone="success" />
        <MetricCard label="ناموفق" value={counts.FAILED} icon={WarningCircle} tone="danger" />
      </section>

      <section className="overview-evidence" aria-label="وضعیت سامانه"><div><Database size={18} /><span>پایگاه داده</span><Badge tone={statusTone(database.data!.status)}>{database.data!.status}</Badge></div><div><PlayCircle size={18} /><span>قابلیت اجرای پس‌زمینه</span><strong>{capabilities.data!.background_execution_available ? "فعال" : "در دسترس نیست"}</strong></div>{counts.RUNNING > 0 && <div><Clock size={18} /><span>جدیدترین اجرای فعال</span><code dir="ltr">{recentRuns.find((run) => run.status === "RUNNING")?.id.slice(0, 12) || "-"}</code></div>}</section>

      <section className="overview-status surface" aria-labelledby="status-distribution-title">
        <div className="surface-header">
          <div><h2 id="status-distribution-title">توزیع وضعیت اجراها</h2><p>بر پایه همه اجراهای بازگردانده‌شده از API فعلی.</p></div>
          <dl className="overview-totals">
            <div><dt>Fallback</dt><dd dir="ltr">{fallbackTotal.toLocaleString("fa-IR")}</dd></div>
            <div><dt>خطاها</dt><dd dir="ltr">{errorTotal.toLocaleString("fa-IR")}</dd></div>
            <div><dt>زیرساخت</dt><dd dir="ltr">{infrastructureErrorTotal.toLocaleString("fa-IR")}</dd></div>
          </dl>
        </div>
        {totalRuns > 0 ? <>
          <div className="status-distribution" role="img" aria-label={statusOrder.map((status) => `${status}: ${counts[status]}`).join(", ")}>
            {statusOrder.map((status) => counts[status] > 0 && <span key={status} className={`status-distribution__segment is-${status.toLowerCase()}`} style={{ width: `${counts[status] / totalRuns * 100}%` }} />)}
          </div>
          <div className="status-legend">{statusOrder.filter((status) => counts[status] > 0).map((status) => <span key={status}><StatusBadge status={status} /><b dir="ltr">{counts[status].toLocaleString("fa-IR")}</b></span>)}</div>
        </> : <p className="empty-inline">هنوز اجرایی ثبت نشده است.</p>}
      </section>

      <section className="surface recent-runs-panel" aria-labelledby="recent-runs-title">
        <div className="surface-header"><div><h2 id="recent-runs-title">اجراهای اخیر</h2><p>آخرین اجراها با شمارنده‌های ثبت‌شده در PostgreSQL.</p></div></div>
        {!recentRuns.length ? <EmptyState title="هنوز اجرایی وجود ندارد" message="پس از ایجاد نخستین اجرا، وضعیت آن در این بخش نمایش داده می‌شود." /> : (
          <div className="table-wrap"><table className="data-table overview-table">
            <thead><tr><th>شناسه اجرا</th><th>نوع</th><th>وضعیت</th><th>پیشرفت نوبت</th><th>Fallback</th><th>خطا</th><th>زیرساخت</th><th>ایجاد</th></tr></thead>
            <tbody>{recentRuns.map((run) => <tr key={run.id}>
              <td><button type="button" className="technical-link" dir="ltr" onClick={() => onRunOpen(run)} title={run.id}>{run.id}</button></td>
              <td><code dir="ltr">{run.run_type}</code></td>
              <td><StatusBadge status={run.status} /></td>
              <td><span dir="ltr" className="technical-value">{run.completed_turns} / {run.total_turns}</span></td>
              <td><span dir="ltr" className="technical-value">{run.fallback_count}</span></td>
              <td><span dir="ltr" className="technical-value">{run.error_count}</span></td>
              <td><span dir="ltr" className="technical-value">{run.infrastructure_error_count}</span></td>
              <td><time dateTime={run.created_at}>{formatDate(run.created_at)}</time></td>
            </tr>)}</tbody>
          </table></div>
        )}
      </section>
    </div>
  );
}
