import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamSse } from "../api/sse";
import { useEvaluationApi } from "../api/context";
import type { SseEvent } from "../types/api";
import { ApiError } from "../api/client";

const TERMINAL = new Set(["run_completed", "run_failed", "run_cancelled"]);

export function useRunEvents(runId: string | null, active: boolean) {
  const api = useEvaluationApi();
  const queryClient = useQueryClient();
  const [lastEvent, setLastEvent] = useState<SseEvent | null>(null);
  const [connection, setConnection] = useState<"connecting" | "live" | "reconnecting" | "closed">("closed");
  const [errorCode, setErrorCode] = useState<string | null>(null);

  useEffect(() => {
    if (!runId || !active) { setConnection("closed"); setErrorCode(null); return; }
    const controller = new AbortController();
    let stopped = false;
    let retryTimer: number | undefined;
    let retryCount = 0;
    let terminalReceived = false;

    const connect = async () => {
      setConnection(retryCount ? "reconnecting" : "connecting");
      try {
        const response = await api.eventResponse(runId, controller.signal);
        if (stopped) return;
        setErrorCode(null);
        setConnection("live");
        await streamSse(response, (event) => {
          setLastEvent(event);
          setErrorCode(null);
          const sessionId = typeof event.data.run_session_id === "string" ? event.data.run_session_id : null;
          const turnId = typeof event.data.run_turn_id === "string" ? event.data.run_turn_id : null;
          if (["snapshot", "progress"].includes(event.event)) {
            void queryClient.invalidateQueries({ queryKey: ["run", runId] });
          }
          if (["session_started", "session_completed"].includes(event.event)) {
            void queryClient.invalidateQueries({ queryKey: ["run-sessions", runId] });
          }
          if (["turn_started", "turn_completed"].includes(event.event)) {
            void queryClient.invalidateQueries({ queryKey: ["run-sessions", runId] });
            if (sessionId) void queryClient.invalidateQueries({ queryKey: ["run-session", sessionId] });
          }
          if (event.event === "stage_completed" && turnId) {
            void queryClient.invalidateQueries({ queryKey: ["turn-trace", turnId] });
          }
          if (TERMINAL.has(event.event)) {
            terminalReceived = true;
            setConnection("closed");
            void queryClient.invalidateQueries({ queryKey: ["run", runId] });
            void queryClient.invalidateQueries({ queryKey: ["run-sessions", runId] });
          }
        });
        if (!stopped && !terminalReceived) {
          retryCount += 1;
          retryTimer = window.setTimeout(connect, Math.min(5_000, retryCount * 1_000));
        }
      } catch (error) {
        if (controller.signal.aborted || stopped) return;
        setErrorCode(error instanceof ApiError ? error.code : "SSE_CONNECTION_UNAVAILABLE");
        retryCount += 1;
        setConnection("reconnecting");
        retryTimer = window.setTimeout(connect, Math.min(8_000, retryCount * 1_500));
      }
    };
    void connect();
    return () => {
      stopped = true;
      controller.abort();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [active, api, queryClient, runId]);

  return { lastEvent, connection, errorCode };
}
