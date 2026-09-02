import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamSse } from "../api/sse";
import { useAuth } from "../app/auth";
import type { SseEvent } from "../types/api";
import { ApiError } from "../api/client";

const TERMINAL = new Set(["run_completed", "run_failed", "run_cancelled"]);

export function useRunEvents(runId: string | null, active: boolean) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const [lastEvent, setLastEvent] = useState<SseEvent | null>(null);
  const [connection, setConnection] = useState<"idle" | "connecting" | "live" | "reconnecting" | "closed">("idle");
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const lastId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!runId || !active) { setConnection("idle"); setErrorCode(null); return; }
    const controller = new AbortController();
    let stopped = false;
    let retryTimer: number | undefined;
    let retryCount = 0;
    let terminalReceived = false;

    const connect = async () => {
      setConnection(retryCount ? "reconnecting" : "connecting");
      try {
        const response = await api.eventResponse(runId, controller.signal, lastId.current);
        if (stopped) return;
        setErrorCode(null);
        setConnection("live");
        await streamSse(response, (event) => {
          if (event.id) lastId.current = event.id;
          setLastEvent(event);
          if (event.event === "redis_unavailable") setErrorCode("EVALUATION_REDIS_UNAVAILABLE");
          else setErrorCode(null);
          void queryClient.invalidateQueries({ queryKey: ["run", runId] });
          if (["session_completed", "turn_completed", "stage_completed", "progress"].includes(event.event)) {
            void queryClient.invalidateQueries({ queryKey: ["run-sessions", runId] });
          }
          if (TERMINAL.has(event.event)) { terminalReceived = true; setConnection("closed"); }
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
