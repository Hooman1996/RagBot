import { FileArrowUp, FileCsv, Warning } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { useAuth } from "../../app/auth";
import type { ImportResponse } from "../../types/api";
import { Button } from "../ui/Button";
import { ErrorState } from "../ui/States";
import { formatBytes } from "../ui/format";

export function DatasetImport({ datasetType, onImported, imported }: { datasetType: "PIPELINE_INSPECTION" | "STABILITY"; onImported: (value: ImportResponse) => void; imported: ImportResponse | null }) {
  const { api } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const upload = useMutation({ mutationFn: () => api.importDataset(file!, datasetType), onSuccess: onImported });
  const choose = (next: File | null) => {
    if (!next) return;
    setFile(next);
  };
  const invalidExtension = file && !/\.(csv|xlsx)$/i.test(file.name);
  const tooLarge = file && capabilities.data && file.size > capabilities.data.max_upload_bytes;
  const drop = (event: DragEvent) => { event.preventDefault(); setDrag(false); choose(event.dataTransfer.files[0] || null); };
  return (
    <section className="import-block" aria-labelledby={`import-${datasetType}`}>
      <div className="section-heading"><div><h2 id={`import-${datasetType}`}>ورودی فایل</h2><p>CSV یا XLSX با ستون اجباری query و ستون‌های اختیاری session_id و time.</p></div></div>
      <div className={`dropzone ${drag ? "is-dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={drop}>
        <FileArrowUp size={36} weight="duotone" />
        <strong>{file ? file.name : "فایل را اینجا رها کنید"}</strong>
        <span>{file ? formatBytes(file.size) : "یا فایل را از دستگاه انتخاب کنید"}</span>
        <input ref={input} type="file" accept=".csv,.xlsx" hidden onChange={(event) => choose(event.target.files?.[0] || null)} />
        <Button type="button" variant="secondary" onClick={() => input.current?.click()}>{file ? "تغییر فایل" : "انتخاب فایل"}</Button>
      </div>
      {(invalidExtension || tooLarge) && <p className="field-error" role="alert">{invalidExtension ? "پسوند فایل باید csv یا xlsx باشد." : `حداکثر حجم مجاز ${formatBytes(capabilities.data!.max_upload_bytes)} است.`}</p>}
      {file && <div className="button-row"><Button onClick={() => upload.mutate()} disabled={!!invalidExtension || !!tooLarge || upload.isPending}>{upload.isPending ? "در حال تحلیل…" : "بارگذاری و تحلیل"}</Button></div>}
      {upload.isError && <ErrorState title="فایل وارد نشد" error={upload.error} />}
      {imported && <ImportSummaryView value={imported} />}
    </section>
  );
}

export function ImportSummaryView({ value }: { value: ImportResponse }) {
  const summary = value.summary;
  const { api } = useAuth();
  const sessionQuery = useQuery({ queryKey: ["dataset-sessions", value.dataset.id], queryFn: () => api.datasetSessions(value.dataset.id) });
  const sessions = sessionQuery.data ? { multi: sessionQuery.data.filter((item) => item.turn_count > 1).length, single: sessionQuery.data.filter((item) => item.turn_count === 1).length } : null;
  return (
    <div className="import-summary" aria-label="خلاصه ورود داده">
      <div className="summary-header"><FileCsv size={24} /><div><strong dir="auto">{summary.filename}</strong><span dir="ltr">SHA256 {summary.file_sha256?.slice(0, 12)}…</span></div></div>
      <dl className="metric-strip">
        <div><dt>ردیف‌ها</dt><dd>{summary.row_count}</dd></div><div><dt>معتبر</dt><dd>{summary.valid_row_count}</dd></div><div><dt>نامعتبر</dt><dd>{summary.invalid_row_count}</dd></div><div><dt>جلسه‌ها</dt><dd>{summary.session_count}</dd></div><div><dt>چندنوبتی</dt><dd>{sessions?.multi ?? "-"}</dd></div><div><dt>تک‌پرسش</dt><dd>{sessions?.single ?? "-"}</dd></div>
      </dl>
      <p className="semantics-note">ردیف‌های دارای session_id مشترک به ترتیب زمانی بازپخش می‌شوند. هر ردیف بدون session_id یک جلسه مستقل است.</p>
      {!!summary.issues.length && <div className="issue-list"><h3><Warning size={19} />هشدارها و خطاهای ورودی</h3>{summary.issues.map((issue, index) => <div className={`issue issue--${issue.severity.toLowerCase()}`} key={`${issue.code}-${index}`}><code>{issue.code}</code><span>{issue.message}</span>{issue.source_row_number && <small>ردیف {issue.source_row_number}</small>}</div>)}</div>}
    </div>
  );
}
