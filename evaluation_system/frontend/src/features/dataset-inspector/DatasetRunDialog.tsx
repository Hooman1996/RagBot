import { Play, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { DatasourcePicker } from "../../components/DatasourcePicker";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { ErrorState } from "../../components/ui/States";
import type { Dataset } from "../../types/api";

export function DatasetRunDialog({ dataset, open, onClose, onRunOpen }: { dataset: Dataset; open: boolean; onClose: () => void; onRunOpen: (id: string) => void }) {
  const api = useEvaluationApi();
  const [documents, setDocuments] = useState<string[]>([]);
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const workerUnavailable = capabilities.data?.background_execution_available === false;
  const run = useMutation({
    mutationFn: () => api.createRun({ dataset_id: dataset.id, run_type: "DATASET_INSPECTION", repeat_count: 1, documents }),
    onSuccess: (value) => { onClose(); onRunOpen(value.id); },
  });
  return <Modal open={open} title="تنظیم اجرای ارزیابی" onClose={onClose} footer={<>
    <Button variant="ghost" onClick={onClose}>انصراف</Button>
    <Button onClick={() => run.mutate()} disabled={workerUnavailable || !documents.length || run.isPending}><Play size={17} weight="fill" />{run.isPending ? "در حال صف‌بندی" : "شروع ارزیابی"}</Button>
  </>}>
    <div className="run-dialog-dataset"><span>مجموعه انتخاب‌شده</span><strong dir="auto">{dataset.filename || dataset.id}</strong><code dir="ltr">{dataset.id}</code></div>
    <DatasourcePicker selected={documents} onChange={setDocuments} />
    {!documents.length && <p className="run-dialog-hint">برای شروع اجرا حداقل یک منبع دانش انتخاب کنید.</p>}
    {workerUnavailable && <div className="service-alert service-alert--danger"><WarningCircle size={19} /><div><strong>اجرای پس‌زمینه در دسترس نیست</strong><p>امکان ایجاد اجرا در تنظیمات سرویس فعال نشده است.</p></div></div>}
    {run.isError && <ErrorState title="اجرای ارزیابی شروع نشد" error={run.error} />}
  </Modal>;
}
