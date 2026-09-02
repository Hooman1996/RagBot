import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { EvaluationApiClient } from "../api/client";

interface AuthValue {
  authenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  api: EvaluationApiClient;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [authenticated, setAuthenticated] = useState(false);
  const api = useMemo(() => new EvaluationApiClient(), []);
  const value = useMemo(() => ({
    authenticated,
    login: async (username: string, password: string) => {
      await api.login(username, password);
      setAuthenticated(true);
    },
    api,
  }), [api, authenticated]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
}
