import { createContext, useContext, useMemo, type PropsWithChildren } from "react";
import { EvaluationApiClient } from "./client";

const EvaluationApiContext = createContext<EvaluationApiClient | null>(null);

export function EvaluationApiProvider({ children }: PropsWithChildren) {
  const api = useMemo(() => new EvaluationApiClient(), []);
  return <EvaluationApiContext.Provider value={api}>{children}</EvaluationApiContext.Provider>;
}

export function useEvaluationApi(): EvaluationApiClient {
  const api = useContext(EvaluationApiContext);
  if (!api) throw new Error("EvaluationApiProvider is missing");
  return api;
}
