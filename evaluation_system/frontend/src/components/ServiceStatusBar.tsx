import { CheckCircle, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../app/auth";

type ServiceState = "ready" | "unavailable" | "checking" | "configured";

function Indicator({ label, state, detail }: { label: string; state: ServiceState; detail: string }) {
  const Icon = state === "ready" ? CheckCircle : state === "unavailable" ? WarningCircle : CircleNotch;
  return <li className={`service-indicator service-indicator--${state}`} title={detail}>
    <Icon size={14} weight={state === "ready" ? "fill" : "bold"} aria-hidden="true" />
    <span>{label}</span>
    <small>{detail}</small>
  </li>;
}

export function ServiceStatusBar() {
  const { api } = useAuth();
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities, staleTime: 30_000, retry: 1 });
  const database = useQuery({ queryKey: ["database-status"], queryFn: api.databaseStatus, staleTime: 30_000, retry: 1 });
  const datasources = useQuery({ queryKey: ["datasources"], queryFn: api.datasources, staleTime: 30_000, retry: 1 });
  const queueAvailable = capabilities.data?.background_execution_available;

  return <div className="service-status" aria-label="وضعیت سرویس‌های ارزیابی">
    <ul>
      <Indicator label="API" state={capabilities.isError ? "unavailable" : capabilities.data ? "ready" : "checking"} detail={capabilities.isError ? "Unavailable" : capabilities.data ? "Reachable" : "Checking"} />
      <Indicator label="Worker" state={queueAvailable === false ? "unavailable" : queueAvailable === true ? "configured" : "checking"} detail={queueAvailable === false ? "Unavailable" : queueAvailable === true ? "Queue configured" : "Checking"} />
      <Indicator label="Redis" state={queueAvailable === false ? "unavailable" : queueAvailable === true ? "configured" : "checking"} detail={queueAvailable === false ? "Unavailable" : queueAvailable === true ? "Verified during live run" : "Checking"} />
      <Indicator label="Database" state={database.isError || (database.data && database.data.status !== "READY") ? "unavailable" : database.data ? "ready" : "checking"} detail={database.data?.status || (database.isError ? "Unavailable" : "Checking")} />
      <Indicator label="RAG dependencies" state={datasources.isError ? "unavailable" : datasources.data ? "ready" : "checking"} detail={datasources.isError ? "Unavailable" : datasources.data ? `${datasources.data.length} datasource${datasources.data.length === 1 ? "" : "s"}` : "Checking"} />
    </ul>
    <span className="service-status__note">وضعیت Worker و Redis هنگام اجرای زنده با SSE تأیید می‌شود.</span>
  </div>;
}
