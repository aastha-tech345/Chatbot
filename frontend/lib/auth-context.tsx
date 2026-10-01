"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { isAuthenticated, logout as doLogout, AuthUser } from "@/lib/auth";

interface AuthCtx {
  user: AuthUser | null;
  ready: boolean;          // false while we're reading sessionStorage on mount
  setUser: (u: AuthUser | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>({
  user: null,
  ready: false,
  setUser: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Rehydrate from sessionStorage on first render (client only)
    if (isAuthenticated()) {
      setUserState({ email: "admin@master-chatbot.local", name: "Aastha" });
    }
    setReady(true);
  }, []);

  const setUser = useCallback((u: AuthUser | null) => {
    setUserState(u);
  }, []);

  const logout = useCallback(() => {
    doLogout();
    setUserState(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
