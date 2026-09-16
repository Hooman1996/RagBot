import { CheckCircle, FileArrowUp, FileCsv, Warning } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { useEvaluationApi } from "../../api/context";
import type { ImportIssue, ImportResponse } from "../../types/api";
import { Button } from "../ui/Button";
import { ErrorState, SkeletonRows } from "../ui/States";
import { formatBytes, shortHash } from "../ui/format";

export function DatasetImport({ datasetType, onImported, imported, compact = false, onInspect }: {
  datasetType: "PIPELINE_INSPECTION" | "STABILITY";
  onImported: (value: ImportResponse) => void | Promise<void>;
  imported: ImportResponse | null;
  compact?: boolean;
  onInspect?: () => void;
}) {
  const api = useEvaluationApi();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const upload = useMutation({ mutationFn: () => api.importDataset(file!, datasetType), onSuccess: onImported });
  const choose = (next: File | null) => { if (next) setFile(next); };
  const allowedTypes = capabilities.data?.file_types?.length ? capabilities.data.file_types.map((item) => item.toLocaleLowerCase().replace(/^\*?\./, "")) : ["csv", "xlsx"];
  const extension = file?.name.split(".").pop()?.toLocaleLowerCase() || "";
  const invalidExtension = !!file && !allowedTypes.includes(extension);
  const tooLarge = !!file && !!capabilities.data && file.size > capabilities.data.max_upload_bytes;
  const drop = (event: DragEvent) => { event.preventDefault(); setDrag(false); choose(event.dataTransfer.files[0] || null); };

  if (capabilities.isLoading) return <SkeletonRows count={3} />;
  return <section className={`import-block ${compact ? "import-block--compact" : ""}`} aria-labelledby={`import-${datasetType}`}>
    {!compact && <div className="section-heading"><div><h2 id={`import-${datasetType}`}>ورودی فایل</h2><p>CSV یا XLSX با ستون اجباری query و ستون‌های اختیاری session_id و time.</p></div></div>}
    {capabilities.isError ? <ErrorState title="محدودیت‌های بارگذاری قابل دریافت نیستند" error={capabilities.error} retry={() => void capabilities.refetch()} /> : !imported ? <>
      <div className="import-guidance"><strong>ساختار فایل</strong><span><code>query</code> الزامی</span><span><code>session_id</code> اختیاری</span><span><code>time</code> اختیاری</span></div>
      <div className={`dropzone ${drag ? "is-dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={drop}>
        <FileArrowUp size={32} weight="duotone" />
        <strong>{file ? file.name : "فایل CSV یا XLSX را اینجا رها کنید"}</strong>
        <span>{file ? formatBytes(file.size) : `حداکثر حجم ${formatBytes(capabilities.data!.max_upload_bytes)}`}</span>
        <input ref={input} type="file" aria-label="انتخاب فایل مجموعه داده" accept={allowedTypes.map((item) => `.${item}`).join(",")} className="sr-only" onChange={(event) => choose(event.target.files?.[0] || null)} />
        <Button type="button" variant="secondary" onClick={() => input.current?.click()}>{file ? "تغییر فایل" : "انتخاب فایل"}</Button>
      </div>
      {(invalidExtension || tooLarge) && <p className="field-error" role="alert">{invalidExtension ? `پسوند فایل باید ${allowedTypes.map((item) => `.${item}`).join(" یا ")} باشد.` : `حداکثر حجم مجاز ${formatBytes(capabilities.data!.max_upload_bytes)} است.`}</p>}
      {file && <div className="button-row import-actions"><Button onClick={() => upload.mutate()} disabled={invalidExtension || tooLarge || upload.isPending}>{upload.isPending ? "در حال بارگذاری و تحلیل" : "بارگذاری و تحلیل"}</Button></div>}
      {upload.isError && <ErrorState title="فایل وارد نشد" error={upload.error} />}
    </> : <ImportSummaryView value={imported} onInspect={onInspect} />}
  </section>;
}

function IssueGroup({ title, issues, tone }: { title: string; issues: ImportIssue[]; tone: "error" | "warning" }) {
  if (!issues.length) return null;
  return <section className={`import-issues import-issues--${tone}`}><h3><Warning size={18} />{title}<span>{issues.length.toLocaleString("fa-IR")}</span></h3><div>{issues.map((issue, index) => <article className="import-issue" key={`${issue.code}-${issue.source_row_number}-${index}`}>
    <code dir="ltr">{issue.code}</code><p>{issue.message}</p>
    <dl>{issue.source_row_number != null && <div><dt>ردیف</dt><dd dir="ltr">{issue.source_row_number}</dd></div>}{issue.field_name && <div><dt>فیلد</dt><dd dir="ltr">{issue.field_name}</dd></div>}</dl>
  </article>)}</div></section>;
}

export function ImportSummaryView({ value, onInspect }: { value: ImportResponse; onInspect?: () => void }) {
  const summary = value.summary;
  const errors = summary.issues.filter((issue) => issue.severity === "ERROR");
  const warnings = summary.issues.filter((issue) => issue.severity === "WARNING");
  return <div className="import-summary import-summary--result" aria-label="خلاصه ورود داده">
    <div className="import-success"><CheckCircle size={24} weight="fill" /><div><strong>مجموعه داده وارد شد</strong><span>اکنون از کتابخانه و بازرس داده در دسترس است.</span></div></div>
    <div className="summary-header"><FileCsv size={24} /><div><strong dir="auto">{summary.filename || value.dataset.filename || value.dataset.id}</strong><span dir="ltr" title={summary.file_sha256 || undefined}>SHA256 {shortHash(summary.file_sha256)}</span></div></div>
    <dl className="metric-strip import-result-metrics">
      <div><dt>ردیف‌ها</dt><dd>{summary.row_count.toLocaleString("fa-IR")}</dd></div><div><dt>معتبر</dt><dd>{summary.valid_row_count.toLocaleString("fa-IR")}</dd></div><div><dt>نامعتبر</dt><dd>{summary.invalid_row_count.toLocaleString("fa-IR")}</dd></div><div><dt>جلسه‌ها</dt><dd>{summary.session_count.toLocaleString("fa-IR")}</dd></div>
    </dl>
    {!!summary.issues.length && <div className="import-issue-groups"><IssueGroup title="خطاها" issues={errors} tone="error" /><IssueGroup title="هشدارها" issues={warnings} tone="warning" /></div>}
    {!summary.issues.length && <p className="import-clean"><CheckCircle size={16} />هیچ مسئله‌ای هنگام ورود گزارش نشد.</p>}
    {onInspect && <div className="button-row import-actions"><Button onClick={onInspect}>مشاهده مجموعه واردشده</Button></div>}
  </div>;
}
