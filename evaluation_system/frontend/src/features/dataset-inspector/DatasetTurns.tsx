import { Info } from "@phosphor-icons/react";
import type { DatasetSession, DatasetTurn } from "../../types/api";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/States";
import { formatDate } from "../../components/ui/format";

export function DatasetTurns({ session, turns }: { session: DatasetSession; turns: DatasetTurn[] }) {
  const ordered = [...turns].sort((a, b) => a.turn_index - b.turn_index);
  return <aside className="dataset-turns surface" aria-labelledby="dataset-turns-title">
    <div className="surface-header dataset-turns__header">
      <div><h2 id="dataset-turns-title">نوبت‌های جلسه</h2><p dir="ltr" title={session.id}>{session.source_session_id || session.id}</p></div>
      <Badge tone={session.synthetic_session ? "warning" : "info"}>{session.turn_count.toLocaleString("fa-IR")} نوبت</Badge>
    </div>
    {session.synthetic_session && <div className="synthetic-note" title="این ردیف منبع session_id مشترک نداشت و به‌صورت یک جلسه ارزیابی مستقل وارد شد."><Info size={17} /><p>این ردیف شناسه جلسه مشترک نداشت و به‌صورت یک جلسه ارزیابی مستقل وارد شد.</p></div>}
    {ordered.length ? <ol className="source-turn-list">{ordered.map((turn) => <li key={turn.id}>
      <div className="source-turn__index"><span>{turn.turn_index.toLocaleString("fa-IR")}</span><small>نوبت</small></div>
      <div className="source-turn__body"><p>{turn.query}</p><dl>
        <div><dt>ردیف منبع</dt><dd dir="ltr">{turn.source_row_number ?? "-"}</dd></div>
        <div><dt>زمان منبع</dt><dd dir="ltr">{formatDate(turn.source_timestamp)}</dd></div>
        {turn.source_time_raw && <div><dt>زمان خام</dt><dd dir="ltr" title={turn.source_time_raw}>{turn.source_time_raw}</dd></div>}
      </dl></div>
    </li>)}</ol> : <EmptyState title="نوبتی ثبت نشده است" message="این جلسه نوبت قابل نمایش ندارد." />}
  </aside>;
}
