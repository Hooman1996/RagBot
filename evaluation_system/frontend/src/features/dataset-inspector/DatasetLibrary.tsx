import { CheckCircle, MagnifyingGlass, Trash, WarningCircle } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { Dataset } from "../../types/api";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { formatDate } from "../../components/ui/format";

export function DatasetLibrary({ datasets, selectedId, deletingId, deleteError, onSelect, onDelete }: {
  datasets: Dataset[];
  selectedId: string | null;
  deletingId: string | null;
  deleteError: unknown;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return needle ? datasets.filter((item) => `${item.filename || ""} ${item.id}`.toLocaleLowerCase().includes(needle)) : datasets;
  }, [datasets, search]);

  return <aside className="dataset-library surface" aria-label="کتابخانه مجموعه داده">
    <div className="surface-header dataset-library__header">
      <div><h2>کتابخانه</h2><p>{datasets.length.toLocaleString("fa-IR")} مجموعه داده</p></div>
    </div>
    <label className="dataset-search">
      <span className="sr-only">جستجوی مجموعه داده</span>
      <MagnifyingGlass size={16} aria-hidden="true" />
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جستجو با نام یا شناسه" />
    </label>
    <div className="dataset-library__list">
      {visible.map((dataset) => {
        const selected = dataset.id === selectedId;
        const confirming = confirmId === dataset.id;
        return <article className={`dataset-item ${selected ? "is-selected" : ""}`} key={dataset.id}>
          <button className="dataset-item__select" aria-pressed={selected} onClick={() => onSelect(dataset.id)}>
            <span className="dataset-item__title" dir="auto">{dataset.filename || `مجموعه ${dataset.id.slice(0, 8)}`}</span>
            <span className="dataset-item__badges">
              <Badge tone={dataset.dataset_type === "PIPELINE_INSPECTION" ? "info" : "neutral"}>{dataset.dataset_type}</Badge>
              <span className={`dataset-health ${dataset.invalid_row_count ? "is-warning" : "is-clean"}`}>
                {dataset.invalid_row_count ? <WarningCircle size={13} weight="bold" /> : <CheckCircle size={13} weight="bold" />}
                {dataset.invalid_row_count ? `${dataset.invalid_row_count.toLocaleString("fa-IR")} نامعتبر` : "بدون ردیف نامعتبر"}
              </span>
            </span>
            <span className="dataset-item__counts">
              <span>{dataset.session_count.toLocaleString("fa-IR")} جلسه</span>
              <span>{dataset.row_count.toLocaleString("fa-IR")} ردیف</span>
              <span>{dataset.source_type}</span>
            </span>
            <time dateTime={dataset.created_at}>{formatDate(dataset.created_at)}</time>
            <code dir="ltr" title={dataset.id}>{dataset.id}</code>
          </button>
          {confirming ? <div className="dataset-delete-confirm" role="group" aria-label="تأیید حذف">
            <span>این مجموعه حذف شود؟</span>
            <Button variant="danger" onClick={() => onDelete(dataset.id)} disabled={deletingId === dataset.id}>{deletingId === dataset.id ? "در حال حذف" : "حذف"}</Button>
            <Button variant="ghost" onClick={() => setConfirmId(null)}>انصراف</Button>
          </div> : <button className="dataset-item__delete" aria-label={`حذف ${dataset.filename || dataset.id}`} title="حذف مجموعه داده" onClick={() => setConfirmId(dataset.id)}><Trash size={16} /></button>}
          {confirming && !!deleteError && <p className="dataset-item__error" role="alert">حذف مجموعه داده انجام نشد.</p>}
        </article>;
      })}
      {!visible.length && <p className="dataset-library__empty">مجموعه‌ای با این عبارت پیدا نشد.</p>}
    </div>
  </aside>;
}
