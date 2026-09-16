import { Funnel, MagnifyingGlass } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { Run } from "../../types/api";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { shortHash } from "../../components/ui/format";

export function PipelineRunPicker({ runs, selectedId, onSelect }: { runs: Run[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("ALL");
  const [type, setType] = useState("ALL");
  const filtered = useMemo(() => [...runs]
    .filter((run) => !search || run.id.toLowerCase().includes(search.toLowerCase()))
    .filter((run) => status === "ALL" || run.status === status)
    .filter((run) => type === "ALL" || run.run_type === type)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), [runs, search, status, type]);

  return <section className="pipeline-picker-section">
    <div className="pipeline-picker-title"><span>اجرا</span><small>{filtered.length} / {runs.length}</small></div>
    <label className="pipeline-search"><span>فیلتر Run ID</span><div><MagnifyingGlass size={14} /><input aria-label="فیلتر Run ID" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Run ID" dir="ltr" /></div></label>
    <div className="pipeline-filter-row"><Funnel size={14} aria-hidden="true" /><select aria-label="فیلتر وضعیت اجرا در Pipeline" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">همه وضعیت‌ها</option>{["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="فیلتر نوع اجرا در Pipeline" value={type} onChange={(event) => setType(event.target.value)}><option value="ALL">همه انواع</option>{["DATASET_INSPECTION", "STABILITY_QUERY", "STABILITY_SESSION", "STABILITY_DATASET"].map((value) => <option key={value}>{value}</option>)}</select></div>
    <div className="pipeline-run-list" aria-label="اجراهای موجود">{filtered.map((run) => <button key={run.id} type="button" className={run.id === selectedId ? "is-selected" : ""} onClick={() => onSelect(run.id)} aria-label={`انتخاب اجرای ${run.id}`}>
      <span className="pipeline-picker-id" dir="ltr" title={run.id}>{shortHash(run.id)}</span><StatusBadge status={run.status} /><small dir="ltr">{run.run_type}</small><small>{run.completed_turns} / {run.total_turns} نوبت</small>
    </button>)}</div>
    {!filtered.length && <p className="pipeline-picker-empty">اجرایی مطابق فیلترهای محلی نیست.</p>}
  </section>;
}
