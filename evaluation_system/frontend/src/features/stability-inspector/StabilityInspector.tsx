import { Chats, FileArrowUp, Play, TextT, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../app/auth";
import { DatasetImport } from "../../components/dataset-import/DatasetImport";
import { DatasourcePicker } from "../../components/DatasourcePicker";
import { RecentRuns } from "../../components/runs/RecentRuns";
import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/States";
import type { ImportResponse } from "../../types/api";
import { ConversationBuilder } from "./ConversationBuilder";
import { StabilityResults } from "./StabilityResults";

type Mode = "single" | "conversation" | "upload";

export function StabilityInspector({ activeRunId, onRunOpen }: { activeRunId: string | null; onRunOpen: (id: string) => void }) {
  const { api } = useAuth(); const [mode, setMode] = useState<Mode>("single");
  const [queries, setQueries] = useState([""]); const [repeat, setRepeat] = useState(3); const [documents, setDocuments] = useState<string[]>([]); const [imported, setImported] = useState<ImportResponse | null>(null);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const repeatMax = capabilities.data?.repeat_max ?? 100;
  const workerUnavailable = capabilities.data?.background_execution_available === false;
  const validQueries = queries.map((item) => item.trim()).filter(Boolean);
  const submit = useMutation({ mutationFn: () => mode === "upload" ? api.createRun({ dataset_id: imported!.dataset.id, run_type: "STABILITY_DATASET", repeat_count: repeat, documents }) : api.manualStability({ queries: validQueries, repeat_count: repeat, documents }), onSuccess: (value) => onRunOpen(value.id) });
  const invalidRepeat = !Number.isInteger(repeat) || repeat < 2 || repeat > repeatMax;
  const repeatError = `عدد صحیح بین ۲ و ${new Intl.NumberFormat("fa-IR").format(repeatMax)} وارد کنید.`;
  const ready = !workerUnavailable && documents.length > 0 && !invalidRepeat && (mode === "upload" ? !!imported && imported.summary.valid_row_count > 0 : validQueries.length === queries.length && validQueries.length > 0);
  return <div className="panel-layout"><header className="panel-header"><div><p className="kicker">Stability / Reproducibility Inspector</p><h1>ردیابی نقطه نخست واگرایی</h1><p>هر تکرار با تاریخچه کاملاً خالی آغاز می‌شود. تفاوت‌ها ثبت می‌شوند، اما داوری معنایی انجام نمی‌شود.</p></div><div className="header-aside"><span>تکرار پیش‌فرض</span><strong>سه اجرای مستقل</strong><span>هم‌زمانی پایداری</span><strong>یک نشست</strong></div></header>
    {activeRunId ? <><StabilityResults runId={activeRunId} /><RecentRuns kind="stability" onOpen={onRunOpen} /></> : <div className="inspector-grid"><div><section className="mode-panel"><div className="mode-tabs" role="tablist"><button role="tab" aria-selected={mode === "single"} onClick={() => { setMode("single"); setQueries([queries[0] || ""]); }}><TextT />پرسش تکی</button><button role="tab" aria-selected={mode === "conversation"} onClick={() => { setMode("conversation"); if (queries.length < 2) setQueries([queries[0] || "", ""]); }}><Chats />مکالمه</button><button role="tab" aria-selected={mode === "upload"} onClick={() => setMode("upload")}><FileArrowUp />فایل</button></div>
      {mode === "single" && <label className="field-stack"><span>پرسش کاربر</span><textarea rows={4} dir="auto" value={queries[0]} onChange={(event) => setQueries([event.target.value])} placeholder="پرسش مورد بررسی را وارد کنید" /></label>}
      {mode === "conversation" && <ConversationBuilder queries={queries} onChange={setQueries} />}
      {mode === "upload" && <DatasetImport datasetType="STABILITY" imported={imported} onImported={setImported} />}
      </section><section className="run-config"><div className="section-heading"><div><h2>تنظیم تکرار</h2><p>پاسخ هر نوبت فقط در همان تکرار وارد تاریخچه می‌شود.</p></div></div><label className="field-stack repeat-field"><span>تعداد تکرار کل نشست</span><input type="number" min={2} max={repeatMax} value={repeat} onChange={(event) => setRepeat(Number(event.target.value))} />{invalidRepeat && <small className="field-error">{repeatError}</small>}</label><DatasourcePicker selected={documents} onChange={setDocuments} />{workerUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={19} /><div><strong>Evaluation worker unavailable</strong><p>اجرای پس‌زمینه در تنظیمات فعال نیست.</p></div></div>}<Button className="start-button" onClick={() => submit.mutate()} disabled={!ready || submit.isPending}><Play weight="fill" />{submit.isPending ? "در حال صف‌بندی…" : "شروع آزمون پایداری"}</Button>{submit.isError && <ErrorState title="آزمون پایداری شروع نشد" error={submit.error} />}</section></div><aside><RecentRuns kind="stability" onOpen={onRunOpen} /></aside></div>}
  </div>;
}
