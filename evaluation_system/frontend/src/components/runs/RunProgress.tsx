import { Broadcast, Check, Clock, Pause, Queue, SpinnerGap, WarningCircle, XCircle } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../app/auth";
import { useRunEvents } from "../../hooks/useRunEvents";
import { Badge, statusTone } from "../ui/Badge";
import { Button } from "../ui/Button";
import { ErrorState, SkeletonRows } from "../ui/States";

const ACTIVE = new Set(["PENDING", "RUNNING"]);

export function RunProgress({ runId }: { runId: string }) {
  const { api } = useAuth(); const client = useQueryClient();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId), refetchInterval: (query) => ACTIVE.has(query.state.data?.status || "") ? 5_000 : false });
  const active = ACTIVE.has(run.data?.status || "");
  const { lastEvent, connection, errorCode } = useRunEvents(runId, active);
  const cancel = useMutation({ mutationFn: () => api.cancelRun(runId), onSuccess: () => client.invalidateQueries({ queryKey: ["run", runId] }) });
  if (run.isLoading) return <SkeletonRows count={2} />;
  if (run.isError) return <ErrorState title="اجرای ارزیابی قابل دریافت نیست" error={run.error} retry={() => void run.refetch()} />;
  const value = run.data!;
  const turnPercent = value.total_turns ? Math.round(value.completed_turns / value.total_turns * 100) : 0;
  const statusLabel = value.status === "PENDING" ? "Queued" : value.status === "RUNNING" ? "Running" : value.status === "COMPLETED" ? "Completed" : value.status === "FAILED" ? "Failed" : "Cancelled";
  const workerUnavailable = errorCode === "EVALUATION_BACKGROUND_EXECUTION_UNAVAILABLE" || errorCode === "EVALUATION_QUEUE_UNAVAILABLE" || value.failure_code === "WORKER_UNAVAILABLE";
  const redisUnavailable = errorCode === "EVALUATION_REDIS_UNAVAILABLE" || (!workerUnavailable && !!errorCode && (errorCode === "HTTP_503" || errorCode.includes("REDIS")));
  const phase = value.status === "PENDING" ? 0 : value.status === "RUNNING" ? 1 : value.status === "COMPLETED" ? 2 : 3;
  return <section className="run-progress" aria-live="polite">
    <div className="run-progress__head"><div><span className={`connection connection--${connection}`}><Broadcast size={16} />{connection === "live" ? "زنده" : connection === "reconnecting" ? "اتصال مجدد" : connection === "closed" ? "پایان یافته" : "در حال اتصال"}</span><h2>اجرای {value.id.slice(0, 8)}</h2></div><div><Badge tone={statusTone(value.status)}>{statusLabel}</Badge>{active && <Button variant="secondary" onClick={() => cancel.mutate()} disabled={cancel.isPending}><Pause size={17} />لغو اجرا</Button>}</div></div>
    <ol className="run-phases" aria-label="وضعیت اجرای ارزیابی">
      <li className={phase >= 0 ? "is-reached" : ""}><Queue /><span>Queued</span></li>
      <li className={phase >= 1 && phase < 3 ? "is-reached" : ""}><SpinnerGap /><span>Running</span></li>
      <li className={phase === 2 ? "is-reached" : ""}><Check /><span>Completed</span></li>
      <li className={phase === 3 ? "is-failed" : ""}><XCircle /><span>Failed</span></li>
    </ol>
    <div className="progress-track" role="progressbar" aria-valuenow={turnPercent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${turnPercent}%` }} /></div>
    <dl className="metric-strip"><div><dt>پیشرفت جلسه</dt><dd>{value.completed_sessions} / {value.total_sessions}</dd></div><div><dt>پیشرفت نوبت</dt><dd>{value.completed_turns} / {value.total_turns}</dd></div><div><dt>Fallback</dt><dd>{value.fallback_count}</dd></div><div><dt>خطای زیرساخت</dt><dd>{value.infrastructure_error_count}</dd></div></dl>
    {lastEvent && <p className="event-caption" dir="ltr">{lastEvent.event}</p>}
    {workerUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={20} /><div><strong>Evaluation worker unavailable</strong><p>صف اجرای ارزیابی در دسترس نیست. Worker را بررسی کنید؛ اجرای HTTP ادامه پیدا نمی‌کند.</p></div></div>}
    {redisUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={20} /><div><strong>Redis unavailable</strong><p>کانال رویداد زنده در دسترس نیست. حقیقت نهایی اجرا همچنان از PostgreSQL بازیابی می‌شود.</p></div></div>}
    {active && connection === "reconnecting" && !workerUnavailable && !redisUnavailable && <div className="service-alert"><Clock size={20} /><div><strong>در انتظار اتصال زنده</strong><p>وضعیت پایدار از سرور هر پنج ثانیه بازخوانی می‌شود.</p></div></div>}
    {value.failure_code && <div className="stage-error"><XCircle size={20} /><div><strong>Run failure</strong><p dir="ltr">{value.failure_code}</p></div></div>}
  </section>;
}
