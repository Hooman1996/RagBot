import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../app/auth";
import { ErrorState, SkeletonRows } from "../ui/States";
import { RunProgress } from "./RunProgress";
import { SessionTable } from "../session-results/SessionTable";

export function RunResults({ runId }: { runId: string }) {
  const { api } = useAuth();
  const sessions = useQuery({ queryKey: ["run-sessions", runId], queryFn: () => api.runSessions(runId), refetchInterval: 5_000 });
  return <div className="run-results"><RunProgress runId={runId} /><div className="section-heading"><div><h2>جلسه‌های ارزیابی</h2><p>هر ردیف یک تاریخچه مستقل است. برای مشاهده نوبت‌ها آن را باز کنید.</p></div></div>{sessions.isLoading ? <SkeletonRows count={5} /> : sessions.isError ? <ErrorState error={sessions.error} retry={() => void sessions.refetch()} /> : <SessionTable sessions={sessions.data!} />}</div>;
}
