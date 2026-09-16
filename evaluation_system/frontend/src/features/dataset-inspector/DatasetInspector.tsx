import { Database, FileText, Plus, Rows, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { DatasetImport } from "../../components/dataset-import/DatasetImport";
import { RecentRuns } from "../../components/runs/RecentRuns";
import { RunResults } from "../../components/runs/RunResults";
import { PageHeader } from "../../components/shell/PageHeader";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { MetricCard } from "../../components/ui/MetricCard";
import { Modal } from "../../components/ui/Modal";
import type { ImportResponse } from "../../types/api";
import { DatasetDetails } from "./DatasetDetails";
import { DatasetLibrary } from "./DatasetLibrary";
import { DatasetRunDialog } from "./DatasetRunDialog";

function newestFirst<T extends { created_at: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => new Date(b.created_at).valueOf() - new Date(a.created_at).valueOf());
}

export function DatasetInspector({ activeRunId, onRunOpen }: { activeRunId: string | null; onRunOpen: (id: string) => void }) {
  const api = useEvaluationApi();
  const queryClient = useQueryClient();
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [imported, setImported] = useState<ImportResponse | null>(null);

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const datasets = useMemo(() => newestFirst(datasetsQuery.data || []), [datasetsQuery.data]);
  useEffect(() => {
    if (!datasets.length) { setSelectedDatasetId(null); return; }
    if (!selectedDatasetId || !datasets.some((item) => item.id === selectedDatasetId)) setSelectedDatasetId(datasets[0].id);
  }, [datasets, selectedDatasetId]);

  const datasetQuery = useQuery({ queryKey: ["dataset", selectedDatasetId], queryFn: () => api.dataset(selectedDatasetId!), enabled: !!selectedDatasetId });
  const selectedDataset = datasetQuery.data || datasets.find((item) => item.id === selectedDatasetId) || null;
  const sessionsQuery = useQuery({ queryKey: ["dataset-sessions", selectedDatasetId], queryFn: () => api.datasetSessions(selectedDatasetId!), enabled: !!selectedDatasetId });
  const sessions = useMemo(() => [...(sessionsQuery.data || [])].sort((a, b) => a.first_source_row - b.first_source_row), [sessionsQuery.data]);
  useEffect(() => { setSelectedSessionId(null); }, [selectedDatasetId]);
  const turnsQuery = useQuery({ queryKey: ["dataset-turns", selectedSessionId], queryFn: () => api.datasetTurns(selectedSessionId!), enabled: !!selectedSessionId });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteDataset(id),
    onSuccess: async (_, deletedId) => {
      const remaining = datasets.filter((item) => item.id !== deletedId);
      if (selectedDatasetId === deletedId) setSelectedDatasetId(remaining[0]?.id || null);
      queryClient.removeQueries({ queryKey: ["dataset", deletedId] });
      queryClient.removeQueries({ queryKey: ["dataset-sessions", deletedId] });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  const handleImported = useCallback(async (value: ImportResponse) => {
    setImported(value);
    setSelectedDatasetId(value.dataset.id);
    queryClient.setQueryData(["dataset", value.dataset.id], value.dataset);
    await queryClient.invalidateQueries({ queryKey: ["datasets"] });
  }, [queryClient]);

  if (activeRunId) return <div className="dataset-page"><PageHeader title="نتیجه ارزیابی" description="نمای فعلی اجرا تا بازطراحی بازرس اجرا در مرحله بعد حفظ شده است." /><RunResults runId={activeRunId} /><section className="surface dataset-recent"><RecentRuns kind="dataset" onOpen={onRunOpen} /></section></div>;

  const totalSessions = datasets.reduce((sum, item) => sum + item.session_count, 0);
  const totalRows = datasets.reduce((sum, item) => sum + item.row_count, 0);
  const totalInvalid = datasets.reduce((sum, item) => sum + item.invalid_row_count, 0);

  return <div className="dataset-page">
    <PageHeader title="مجموعه داده‌ها" description="مجموعه‌های واقعی ارزیابی را مدیریت کنید، نشست‌ها و نوبت‌ها را ببینید و اجرای جدید بسازید." meta={<Button onClick={() => { setImported(null); setImportOpen(true); }}><Plus size={17} weight="bold" />افزودن مجموعه داده</Button>} />

    {datasetsQuery.isLoading ? <div className="dataset-page-loading"><SkeletonRows count={5} /></div> : datasetsQuery.isError ? <ErrorState title="فهرست مجموعه داده‌ها قابل دریافت نیست" error={datasetsQuery.error} retry={() => void datasetsQuery.refetch()} /> : !datasets.length ? <EmptyState title="هنوز مجموعه داده‌ای وجود ندارد" message="یک فایل CSV یا XLSX وارد کنید تا بازرسی نشست‌ها و اجرای ارزیابی آغاز شود." action={<Button onClick={() => setImportOpen(true)}><Plus size={17} />افزودن مجموعه داده</Button>} /> : <>
      <section className="dataset-overview-metrics" aria-label="خلاصه مجموعه داده‌ها">
        <MetricCard label="مجموعه‌ها" value={datasets.length} icon={Database} />
        <MetricCard label="همه جلسه‌ها" value={totalSessions} icon={FileText} />
        <MetricCard label="همه ردیف‌ها" value={totalRows} icon={Rows} />
        <MetricCard label="ردیف نامعتبر" value={totalInvalid} icon={WarningCircle} tone={totalInvalid ? "warning" : "success"} />
      </section>
      <div className="dataset-workspace">
        <DatasetLibrary datasets={datasets} selectedId={selectedDatasetId} deletingId={remove.isPending ? remove.variables : null} deleteError={remove.isError ? remove.error : null} onSelect={setSelectedDatasetId} onDelete={(id) => remove.mutate(id)} />
        {datasetQuery.isLoading && !selectedDataset ? <section className="surface dataset-loading"><SkeletonRows count={6} /></section> : datasetQuery.isError ? <ErrorState title="جزئیات مجموعه داده قابل دریافت نیست" error={datasetQuery.error} retry={() => void datasetQuery.refetch()} /> : selectedDataset && <DatasetDetails
          dataset={selectedDataset}
          sessions={sessions}
          sessionsLoading={sessionsQuery.isLoading}
          sessionsError={sessionsQuery.error}
          selectedSessionId={selectedSessionId}
          turns={turnsQuery.data || []}
          turnsLoading={turnsQuery.isLoading}
          turnsError={turnsQuery.error}
          onSessionSelect={setSelectedSessionId}
          onSessionsRetry={() => void sessionsQuery.refetch()}
          onTurnsRetry={() => void turnsQuery.refetch()}
          onRunRequest={() => setRunOpen(true)}
        />}
      </div>
      <details className="dataset-recent surface"><summary>اجراهای اخیر ارزیابی</summary><div><RecentRuns kind="dataset" onOpen={onRunOpen} /></div></details>
    </>}

    <Modal open={importOpen} title="افزودن مجموعه داده" onClose={() => setImportOpen(false)}>
      <DatasetImport datasetType="PIPELINE_INSPECTION" imported={imported} onImported={handleImported} compact onInspect={() => setImportOpen(false)} />
    </Modal>
    {selectedDataset && <DatasetRunDialog dataset={selectedDataset} open={runOpen} onClose={() => setRunOpen(false)} onRunOpen={onRunOpen} />}
  </div>;
}
