import { MagnifyingGlass } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { RunTurn } from "../../types/api";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDuration } from "../../components/ui/format";

export function PipelineTurnPicker({ turns, selectedId, divergentTurn, onSelect }: { turns: RunTurn[]; selectedId: string | null; divergentTurn?: number | null; onSelect: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [intent, setIntent] = useState("ALL");
  const [signal, setSignal] = useState("ALL");
  const intents = useMemo(() => [...new Set(turns.map((item) => item.actual_intent).filter(Boolean) as string[])].sort(), [turns]);
  const filtered = useMemo(() => turns
    .filter((turn) => !search || turn.raw_query.toLowerCase().includes(search.toLowerCase()))
    .filter((turn) => intent === "ALL" || turn.actual_intent === intent)
    .filter((turn) => signal === "ALL" || (signal === "FALLBACK" ? turn.fallback_used : turn.infrastructure_error || !!turn.error_code || turn.status === "ERROR")), [intent, search, signal, turns]);
  return <section className="pipeline-picker-section pipeline-turn-picker">
    <div className="pipeline-picker-title"><span>نوبت</span><small>{filtered.length} / {turns.length}</small></div>
    <label className="pipeline-search"><span>فیلتر پرسش در جلسه انتخاب‌شده</span><div><MagnifyingGlass size={14} /><input aria-label="فیلتر پرسش در جلسه انتخاب‌شده" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="بخشی از پرسش" /></div></label>
    <div className="pipeline-filter-grid"><select aria-label="فیلتر Intent نوبت" value={intent} onChange={(event) => setIntent(event.target.value)}><option value="ALL">همه Intentها</option>{intents.map((value) => <option key={value}>{value}</option>)}</select><select aria-label="فیلتر رخداد نوبت" value={signal} onChange={(event) => setSignal(event.target.value)}><option value="ALL">همه رخدادها</option><option value="FALLBACK">دارای Fallback</option><option value="ERROR">دارای خطا</option></select></div>
    <div className="pipeline-turn-list">{filtered.map((turn) => <button key={turn.id} type="button" className={turn.id === selectedId ? "is-selected" : ""} onClick={() => onSelect(turn.id)} aria-label={`انتخاب نوبت ${turn.turn_index}: ${turn.raw_query}`}>
      <span className="turn-index">{turn.turn_index}</span><strong dir="auto">{turn.raw_query}</strong><StatusBadge status={turn.infrastructure_error || turn.status === "ERROR" ? "FAILED" : turn.status} /><small dir="ltr">{turn.actual_intent || "Intent unavailable"}</small><small>{formatDuration(turn.total_latency_ms)}</small>{turn.fallback_used && <span className="turn-flag is-fallback">Fallback</span>}{turn.infrastructure_error && <span className="turn-flag is-error">Infra</span>}{divergentTurn === turn.turn_index && <span className="pipeline-divergence">اولین نوبت واگرا</span>}
    </button>)}</div>
    {!filtered.length && <p className="pipeline-picker-empty">نوبتی مطابق فیلترهای این جلسه نیست.</p>}
  </section>;
}
