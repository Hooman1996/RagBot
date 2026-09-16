import { MagnifyingGlass } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { DatasetSession } from "../../types/api";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/States";
import { formatDate } from "../../components/ui/format";

type SessionFilter = "all" | "source" | "synthetic";

export function DatasetSessions({ sessions, selectedId, onSelect }: { sessions: DatasetSession[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SessionFilter>("all");
  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return sessions.filter((session) => {
      if (filter === "synthetic" && !session.synthetic_session) return false;
      if (filter === "source" && session.synthetic_session) return false;
      return !needle || `${session.source_session_id || ""} ${session.id}`.toLocaleLowerCase().includes(needle);
    });
  }, [filter, search, sessions]);

  return <section className="dataset-sessions surface" aria-labelledby="dataset-sessions-title">
    <div className="surface-header">
      <div><h2 id="dataset-sessions-title">جلسه‌های واردشده</h2><p>{sessions.length.toLocaleString("fa-IR")} جلسه، مرتب‌شده بر اساس ردیف منبع</p></div>
    </div>
    <div className="dataset-table-tools">
      <label className="dataset-search">
        <span className="sr-only">جستجوی جلسه</span><MagnifyingGlass size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="شناسه جلسه" />
      </label>
      <label className="dataset-filter"><span>نوع جلسه</span><select value={filter} onChange={(event) => setFilter(event.target.value as SessionFilter)}><option value="all">همه</option><option value="source">دارای شناسه منبع</option><option value="synthetic">جلسه مستقل</option></select></label>
    </div>
    {visible.length ? <div className="table-wrap"><table className="data-table dataset-session-table">
      <thead><tr><th>جلسه منبع</th><th>نوع</th><th>نوبت</th><th>ردیف نخست</th><th>زمان نخست</th><th>زمان آخر</th></tr></thead>
      <tbody>{visible.map((session) => <tr key={session.id} className={selectedId === session.id ? "is-selected" : ""}>
        <td><button className="session-select" onClick={() => onSelect(session.id)} aria-pressed={selectedId === session.id}><span dir="ltr">{session.source_session_id || session.id}</span><small dir="ltr">{session.id}</small></button></td>
        <td>{session.synthetic_session ? <Badge tone="warning">جلسه مستقل</Badge> : <Badge tone="success">جلسه منبع</Badge>}</td>
        <td dir="ltr">{session.turn_count}</td><td dir="ltr">{session.first_source_row}</td>
        <td><time dir="ltr" dateTime={session.first_source_timestamp || undefined}>{formatDate(session.first_source_timestamp)}</time></td>
        <td><time dir="ltr" dateTime={session.last_source_timestamp || undefined}>{formatDate(session.last_source_timestamp)}</time></td>
      </tr>)}</tbody>
    </table></div> : <EmptyState title="جلسه‌ای پیدا نشد" message="عبارت جستجو یا فیلتر نوع جلسه را تغییر دهید." />}
  </section>;
}
