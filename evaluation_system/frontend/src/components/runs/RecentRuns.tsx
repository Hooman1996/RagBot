import { ArrowClockwise, CaretLeft } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../app/auth";
import type { Run } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "../ui/States";
import { formatDate } from "../ui/format";

export function RecentRuns({ kind, onOpen }: { kind: "dataset" | "stability"; onOpen: (id: string) => void }) {
  const { api } = useAuth();
  const query = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  if (query.isLoading) return <SkeletonRows count={3} />;
  if (query.isError) return <ErrorState title="فهرست اجراها قابل دریافت نیست" error={query.error} retry={() => void query.refetch()} />;
  const filtered = query.data!.filter((run) => kind === "dataset" ? run.run_type === "DATASET_INSPECTION" : run.run_type.startsWith("STABILITY")).slice(0, 8);
  if (!filtered.length) return <EmptyState title="اجرای قبلی وجود ندارد" message="پس از شروع نخستین ارزیابی، نتیجه پایدار اینجا قابل بازگشایی است." />;
  return <div className="recent-runs"><div className="section-heading"><div><h2>اجراهای اخیر</h2><p>نتیجه‌ها از PostgreSQL بازخوانی می‌شوند.</p></div><Button variant="ghost" onClick={() => void query.refetch()}><ArrowClockwise size={18} />تازه‌سازی</Button></div>{filtered.map((run: Run) => <button key={run.id} className="run-row" onClick={() => onOpen(run.id)}><span dir="ltr">{run.id.slice(0, 8)}</span><span>{formatDate(run.created_at)}</span><span>{run.completed_turns} / {run.total_turns} نوبت</span><Badge tone={statusTone(run.status)}>{run.status}</Badge><CaretLeft /></button>)}</div>;
}
