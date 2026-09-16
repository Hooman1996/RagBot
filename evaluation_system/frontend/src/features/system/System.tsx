import { CheckCircle, Clock, Database, HardDrives, Link, Pulse, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useEvaluationApi } from "../../api/context";
import { PageHeader } from "../../components/shell/PageHeader";
import { Badge } from "../../components/ui/Badge";
import { ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatBytes, formatDate } from "../../components/ui/format";

const activeStatuses = new Set(["PENDING", "RUNNING"]);

function relativeTime(value: string | null): string {
  if (!value) return "-";
  const milliseconds = Date.now() - Date.parse(value);
  if (!Number.isFinite(milliseconds)) return value;
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  if (seconds < 60) return `${seconds.toLocaleString("fa-IR")} ثانیه پیش`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes.toLocaleString("fa-IR")} دقیقه پیش`;
  return formatDate(value);
}

export function System() {
  const api = useEvaluationApi();
  const database = useQuery({ queryKey: ["database-status"], queryFn: api.databaseStatus, refetchInterval: 30_000 });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities, staleTime: 30_000 });
  const datasources = useQuery({ queryKey: ["datasources"], queryFn: api.datasources, retry: false });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  const evidence = useMemo(() => {
    const values = runs.data || [];
    const pending = values.filter((run) => run.status === "PENDING");
    const running = values.filter((run) => run.status === "RUNNING");
    const failed = values.filter((run) => run.status === "FAILED");
    const heartbeats = values.filter((run) => activeStatuses.has(run.status) && run.heartbeat_at).sort((a, b) => Date.parse(b.heartbeat_at!) - Date.parse(a.heartbeat_at!));
    const oldestPending = [...pending].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))[0];
    return { pending: pending.length, running: running.length, failed: failed.length, latestHeartbeat: heartbeats[0]?.heartbeat_at || null, oldestPending: oldestPending?.created_at || null };
  }, [runs.data]);

  return <div className="system-page">
    <PageHeader title="سیستم و عملیات" description="وضعیت پایگاه داده، قابلیت‌های پیکربندی‌شده و شواهد عملیاتی موجود در API." />
    <section className="system-grid">
      <article className="surface system-status" aria-labelledby="database-status-title">
        <div className="surface-header"><div><h2 id="database-status-title">وضعیت پایگاه داده</h2><p>DatabaseGate مرجع تصمیم‌گیری برای آماده‌سازی پایگاه داده است.</p></div><Database size={22} /></div>
        {database.isLoading ? <SkeletonRows count={3} /> : database.isError ? <ErrorState title="وضعیت پایگاه داده دریافت نشد" error={database.error} retry={() => void database.refetch()} /> : <div className="system-body">
          <div className="system-primary-state"><Badge tone={database.data!.status === "READY" ? "success" : database.data!.status === "ERROR" ? "danger" : "warning"}>{database.data!.status}</Badge><span>{database.data!.status === "READY" ? "پایگاه داده برای ارزیابی آماده است." : "برای اقدام ایمن از راهنمای DatabaseGate استفاده کنید."}</span></div>
          <dl className="system-definitions"><div><dt>Current revision</dt><dd dir="ltr">{database.data!.current_revision || "-"}</dd></div><div><dt>Required revision</dt><dd dir="ltr">{database.data!.required_revision || "-"}</dd></div><div><dt>Initialize allowed</dt><dd>{database.data!.allow_initialize ? "بله" : "خیر"}</dd></div><div><dt>Error code</dt><dd dir="ltr">{database.data!.error_code || "-"}</dd></div></dl>
          {!!database.data!.missing_objects.length && <div className="system-missing"><strong>اشیای مفقود</strong><code dir="ltr">{database.data!.missing_objects.join(", ")}</code></div>}
        </div>}
      </article>

      <article className="surface system-status" aria-labelledby="reachability-title">
        <div className="surface-header"><div><h2 id="reachability-title">دسترسی به منبع داده RagBot</h2><p>این بررسی فقط endpoint فهرست منابع داده را از مسیر Eval API می‌سنجد.</p></div><Link size={22} /></div>
        <div className="system-body">{datasources.isLoading ? <SkeletonRows count={2} /> : datasources.isSuccess ? <div className="reachability-state is-ready"><CheckCircle size={22} weight="fill" /><div><strong>RagBot datasource endpoint reachable</strong><span>{datasources.data.length.toLocaleString("fa-IR")} منبع داده بازگردانده شد.</span></div></div> : <div className="reachability-state is-error"><WarningCircle size={22} weight="fill" /><div><strong>RagBot datasource lookup unavailable</strong><span>این نتیجه وضعیت مدل، GPU یا سرویس تولید را مشخص نمی‌کند.</span></div></div>}</div>
      </article>
    </section>

    <section className="surface" aria-labelledby="operations-title">
      <div className="surface-header"><div><h2 id="operations-title">شواهد اجراهای ثبت‌شده</h2><p>شمارش فقط بر پایه اجراهای بازگردانده‌شده از API فعلی است و معیار رسمی عمق صف نیست.</p></div><Pulse size={22} /></div>
      {runs.isLoading ? <SkeletonRows count={3} /> : runs.isError ? <ErrorState title="اجراها دریافت نشدند" error={runs.error} retry={() => void runs.refetch()} /> : <div className="operations-evidence">
        <dl className="operations-counts"><div><dt>Pending runs</dt><dd>{evidence.pending.toLocaleString("fa-IR")}</dd></div><div><dt>Active runs</dt><dd>{evidence.running.toLocaleString("fa-IR")}</dd></div><div><dt>Failed runs</dt><dd>{evidence.failed.toLocaleString("fa-IR")}</dd></div></dl>
        <dl className="operations-times"><div><Clock size={18} /><dt>آخرین heartbeat اجرای فعال</dt><dd>{relativeTime(evidence.latestHeartbeat)}</dd></div><div><Clock size={18} /><dt>قدیمی‌ترین اجرای در انتظار</dt><dd>{evidence.oldestPending ? formatDate(evidence.oldestPending) : "-"}</dd></div></dl>
      </div>}
    </section>

    <section className="surface" aria-labelledby="capabilities-title">
      <div className="surface-header"><div><h2 id="capabilities-title">قابلیت‌ها و محدودیت‌ها</h2><p>مقادیر پیکربندی هستند و به معنی سلامت لحظه‌ای worker نیستند.</p></div><HardDrives size={22} /></div>
      {capabilities.isLoading ? <SkeletonRows count={4} /> : capabilities.isError ? <ErrorState title="قابلیت‌ها دریافت نشدند" error={capabilities.error} retry={() => void capabilities.refetch()} /> : <dl className="capability-grid">
        <div><dt>نوع فایل</dt><dd dir="ltr">{capabilities.data!.file_types.join(", ")}</dd></div><div><dt>حداکثر بارگذاری</dt><dd dir="ltr">{formatBytes(capabilities.data!.max_upload_bytes)}</dd></div><div><dt>حداکثر ردیف داده</dt><dd>{capabilities.data!.max_dataset_rows.toLocaleString("fa-IR")}</dd></div><div><dt>هم‌زمانی نشست</dt><dd>{capabilities.data!.session_concurrency.toLocaleString("fa-IR")}</dd></div><div><dt>هم‌زمانی پایداری</dt><dd>{capabilities.data!.stability_default_concurrency.toLocaleString("fa-IR")}</dd></div><div><dt>حداکثر تکرار</dt><dd>{capabilities.data!.repeat_max.toLocaleString("fa-IR")}</dd></div><div><dt>قابلیت اجرای پس‌زمینه</dt><dd>{capabilities.data!.background_execution_available ? "فعال" : "در دسترس نیست"}</dd></div><div><dt>قابلیت راه‌اندازی پایگاه داده</dt><dd>{capabilities.data!.allow_database_initialize ? "فعال" : "غیرفعال"}</dd></div>
      </dl>}
    </section>

    <section className="technical-panel" aria-label="اطلاعات فنی سمت کاربر"><div><span>Evaluation API base URL</span><code dir="ltr">{api.baseUrl}</code></div><div><span>DB migration revision</span><code dir="ltr">{database.data?.current_revision || "-"}</code></div></section>
  </div>;
}
