import { Chats, FileArrowUp, Play, TextT, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { DatasetImport } from "../../components/dataset-import/DatasetImport";
import { DatasourcePicker } from "../../components/DatasourcePicker";
import { RecentRuns } from "../../components/runs/RecentRuns";
import { PageHeader } from "../../components/shell/PageHeader";
import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/States";
import type { ImportResponse } from "../../types/api";
import { ConversationBuilder } from "./ConversationBuilder";

type Mode = "single" | "conversation" | "upload";
const modes = [
  { id: "single" as const, label: "پرسش تکی", english: "Single Query", icon: TextT },
  { id: "conversation" as const, label: "مکالمه", english: "Session / Conversation", icon: Chats },
  { id: "upload" as const, label: "مجموعه داده", english: "Dataset", icon: FileArrowUp },
];

export function StabilityRunSetup({ onRunOpen }: { onRunOpen: (id: string) => void }) {
  const api = useEvaluationApi();
  const [mode, setMode] = useState<Mode>("single");
  const [queries, setQueries] = useState([""]);
  const [repeat, setRepeat] = useState(3);
  const [documents, setDocuments] = useState<string[]>([]);
  const [imported, setImported] = useState<ImportResponse | null>(null);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const repeatMax = capabilities.data?.repeat_max ?? 100;
  const workerUnavailable = capabilities.data?.background_execution_available === false;
  const validQueries = queries.map((item) => item.trim()).filter(Boolean);
  const submit = useMutation({ mutationFn: () => mode === "upload" ? api.createRun({ dataset_id: imported!.dataset.id, run_type: "STABILITY_DATASET", repeat_count: repeat, documents }) : api.manualStability({ queries: validQueries, repeat_count: repeat, documents }), onSuccess: (value) => onRunOpen(value.id) });
  const invalidRepeat = !Number.isInteger(repeat) || repeat < 2 || repeat > repeatMax;
  const repeatError = `عدد صحیح بین ۲ و ${new Intl.NumberFormat("fa-IR").format(repeatMax)} وارد کنید.`;
  const validInput = mode === "single" ? queries.length === 1 && validQueries.length === 1 : mode === "conversation" ? queries.length >= 2 && validQueries.length === queries.length : !!imported && imported.summary.valid_row_count > 0;
  const ready = !workerUnavailable && documents.length > 0 && !invalidRepeat && validInput;
  const chooseMode = (next: Mode) => { setMode(next); if (next === "single") setQueries([queries[0] || ""]); if (next === "conversation" && queries.length < 2) setQueries([queries[0] || "", ""]); };

  return <div className="stability-page">
    <PageHeader title="پایداری و تکرارپذیری" description="یک ورودی یکسان مستقل تکرار می‌شود تا تفاوت‌ها دیده شوند. این ابزار درباره کیفیت معنایی پاسخ داوری نمی‌کند." meta={<span className="page-header-english" dir="ltr">Stability / Reproducibility</span>} />
    <div className="stability-setup-layout"><div className="stability-setup-main">
      <section className="mode-panel" aria-labelledby="stability-mode-title"><div className="section-heading"><div><h2 id="stability-mode-title">نوع آزمون</h2><p>ورودی هر تکرار مستقل است و تاریخچه فقط درون همان تکرار ادامه پیدا می‌کند.</p></div></div>
        <div className="mode-tabs" role="tablist" aria-label="نوع آزمون پایداری">{modes.map(({ id, label, english, icon: Icon }) => <button key={id} role="tab" aria-selected={mode === id} onClick={() => chooseMode(id)}><Icon size={18} /><span>{label}<small dir="ltr">{english}</small></span></button>)}</div>
        {mode === "single" && <label className="field-stack"><span>پرسش کاربر</span><textarea rows={4} dir="auto" value={queries[0]} onChange={(event) => setQueries([event.target.value])} placeholder="پرسش مورد بررسی را وارد کنید" /></label>}
        {mode === "conversation" && <ConversationBuilder queries={queries} onChange={setQueries} />}
        {mode === "upload" && <DatasetImport datasetType="STABILITY" imported={imported} onImported={setImported} compact />}
      </section>
      <section className="run-config"><div className="section-heading"><div><h2>پیکربندی تکرار</h2><p>کنترل دما یا seed در قرارداد فعلی وجود ندارد.</p></div></div>
        <div className="stability-config-grid"><label className="field-stack repeat-field"><span>تعداد تکرار</span><input aria-describedby="repeat-help" type="number" min={2} max={repeatMax} value={repeat} onChange={(event) => setRepeat(Number(event.target.value))} /><small id="repeat-help">حداقل ۲، حداکثر {repeatMax.toLocaleString("fa-IR")}</small>{invalidRepeat && <small className="field-error">{repeatError}</small>}</label><DatasourcePicker selected={documents} onChange={setDocuments} /></div>
        {workerUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={19} /><div><strong>Background execution unavailable</strong><p>قابلیت اجرای پس‌زمینه در تنظیمات فعال نیست.</p></div></div>}
        <div className="stability-submit"><Button className="start-button" onClick={() => submit.mutate()} disabled={!ready || submit.isPending}><Play weight="fill" />{submit.isPending ? "در حال صف‌بندی..." : "شروع آزمون پایداری"}</Button><span>نوع اجرا: <code dir="ltr">{mode === "single" ? "STABILITY_QUERY" : mode === "conversation" ? "STABILITY_SESSION" : "STABILITY_DATASET"}</code></span></div>
        {submit.isError && <ErrorState title="آزمون پایداری شروع نشد" error={submit.error} />}
      </section>
    </div><aside><RecentRuns kind="stability" onOpen={onRunOpen} /></aside></div>
  </div>;
}
