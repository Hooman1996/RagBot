import { Play, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../app/auth";
import { DatasetImport } from "../../components/dataset-import/DatasetImport";
import { DatasourcePicker } from "../../components/DatasourcePicker";
import { RecentRuns } from "../../components/runs/RecentRuns";
import { RunResults } from "../../components/runs/RunResults";
import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/States";
import type { ImportResponse } from "../../types/api";

export function DatasetInspector({ activeRunId, onRunOpen }: { activeRunId: string | null; onRunOpen: (id: string) => void }) {
  const { api } = useAuth();
  const [imported, setImported] = useState<ImportResponse | null>(null);
  const [documents, setDocuments] = useState<string[]>([]);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const workerUnavailable = capabilities.data?.background_execution_available === false;
  const run = useMutation({
    mutationFn: () => api.createRun({ dataset_id: imported!.dataset.id, run_type: "DATASET_INSPECTION", repeat_count: 1, documents }),
    onSuccess: (value) => onRunOpen(value.id),
  });
  return <div className="panel-layout">
    <header className="panel-header"><div><p className="kicker">Dataset Session Inspector</p><h1>بازپخش دقیق نشست‌ها</h1><p>رفتار واقعی RagBot را برای فایل‌های تاریخی، با تاریخچه جدا و اثر کامل هر مرحله بررسی کنید.</p></div><div className="header-aside"><span>ترتیب</span><strong>زمان سپس ردیف منبع</strong><span>ردیف بی‌جلسه</span><strong>یک نشست مستقل</strong></div></header>
    {activeRunId ? <><RunResults runId={activeRunId} /><RecentRuns kind="dataset" onOpen={onRunOpen} /></> : <div className="inspector-grid"><div className="dataset-workbench"><DatasetImport datasetType="PIPELINE_INSPECTION" imported={imported} onImported={setImported} /><section className="run-config"><div className="section-heading"><div><h2>منبع داده و اجرا</h2><p>فایل را تحلیل کنید، منبع دانش را برگزینید و اجرا را وارد صف کنید.</p></div></div><DatasourcePicker selected={documents} onChange={setDocuments} />{workerUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={19} /><div><strong>Evaluation worker unavailable</strong><p>اجرای پس‌زمینه در تنظیمات فعال نیست.</p></div></div>}<Button className="start-button" onClick={() => run.mutate()} disabled={workerUnavailable || !imported || !documents.length || imported.summary.valid_row_count === 0 || run.isPending}><Play weight="fill" />{run.isPending ? "در حال صف‌بندی…" : "شروع ارزیابی"}</Button>{!imported && <p className="config-hint">شروع اجرا پس از تحلیل موفق فایل فعال می‌شود.</p>}{run.isError && <ErrorState title="اجرای ارزیابی شروع نشد" error={run.error} />}</section></div><aside><RecentRuns kind="dataset" onOpen={onRunOpen} /></aside></div>}
  </div>;
}
