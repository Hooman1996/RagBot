import { useMemo, useState } from "react";
import type { RunSession } from "../../types/api";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDuration } from "../../components/ui/format";

export function PipelineSessionPicker({ sessions, selectedId, onSelect }: { sessions: RunSession[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const [status, setStatus] = useState("ALL");
  const [signal, setSignal] = useState("ALL");
  const [repeat, setRepeat] = useState("ALL");
  const repeats = useMemo(() => [...new Set(sessions.map((item) => item.repeat_index))].sort((a, b) => a - b), [sessions]);
  const filtered = useMemo(() => sessions
    .filter((item) => status === "ALL" || item.status === status)
    .filter((item) => repeat === "ALL" || item.repeat_index === Number(repeat))
    .filter((item) => signal === "ALL" || (signal === "FALLBACK" ? item.fallback_count > 0 : item.error_count > 0 || item.infrastructure_error_count > 0)), [repeat, sessions, signal, status]);
  return <section className="pipeline-picker-section">
    <div className="pipeline-picker-title"><span>جلسه / تکرار</span><small>{filtered.length} / {sessions.length}</small></div>
    <div className="pipeline-filter-grid"><select aria-label="فیلتر وضعیت جلسه" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">همه وضعیت‌ها</option>{["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="فیلتر رخداد جلسه" value={signal} onChange={(event) => setSignal(event.target.value)}><option value="ALL">همه رخدادها</option><option value="FALLBACK">دارای Fallback</option><option value="ERROR">دارای خطا</option></select><select aria-label="فیلتر تکرار جلسه" value={repeat} onChange={(event) => setRepeat(event.target.value)}><option value="ALL">همه تکرارها</option>{repeats.map((value) => <option key={value} value={value}>تکرار {value}</option>)}</select></div>
    <div className="pipeline-session-list">{filtered.map((session) => <button key={session.id} type="button" className={session.id === selectedId ? "is-selected" : ""} onClick={() => onSelect(session.id)} aria-label={`انتخاب جلسه ${session.source_session_id || session.synthetic_label || session.id}`}>
      <strong dir="auto">{session.source_session_id || session.synthetic_label || "جلسه مصنوعی"}</strong><StatusBadge status={session.status} /><small>تکرار {session.repeat_index}</small><small>{session.turn_count} نوبت</small><small>{formatDuration(session.total_latency_ms)}</small><code dir="ltr">F {session.fallback_count} / E {session.error_count} / I {session.infrastructure_error_count}</code>{session.first_divergent_turn != null && <span className="pipeline-divergence">واگرایی: نوبت {session.first_divergent_turn}، {session.first_divergent_stage}</span>}
    </button>)}</div>
    {!filtered.length && <p className="pipeline-picker-empty">جلسه‌ای مطابق فیلترهای محلی نیست.</p>}
  </section>;
}
