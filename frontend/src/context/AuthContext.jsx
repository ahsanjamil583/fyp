import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getBusinessMe, refreshBusinessAuth } from "../services/authApi.js";

const AuthContext = createContext(null);
const accessKey = "bizxus_business_access_token";
const refreshKey = "bizxus_business_refresh_token";
const userKey = "bizxus_business_user";

function readBusinessSessionValue(key) {
  const sessionValue = sessionStorage.getItem(key);
  if (sessionValue) {
    return sessionValue;
  }

  const legacyValue = localStorage.getItem(key);
  if (legacyValue) {
    sessionStorage.setItem(key, legacyValue);
    localStorage.removeItem(key);
    return legacyValue;
  }

  return null;
}

export function AuthProvider({ children }) {
  const [user, setUserState] = useState(() => {
    const saved = readBusinessSessionValue(userKey);
    if (!saved) return null;
    try {
      return JSON.parse(saved);
    } catch {
      sessionStorage.removeItem(userKey);
      localStorage.removeItem(userKey);
      return null;
    }
  });
  const [token, setTokenState] = useState(() => readBusinessSessionValue(accessKey));
  const [isAuthReady, setIsAuthReady] = useState(false);

  const setSession = useCallback((session) => {
    sessionStorage.setItem(accessKey, session.accessToken);
    sessionStorage.setItem(refreshKey, session.refreshToken);
    sessionStorage.setItem(userKey, JSON.stringify(session.user));
    localStorage.removeItem(accessKey);
    localStorage.removeItem(refreshKey);
    localStorage.removeItem(userKey);
    setTokenState(session.accessToken);
    setUserState(session.user);
  }, []);

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(accessKey);
    sessionStorage.removeItem(refreshKey);
    sessionStorage.removeItem(userKey);
    localStorage.removeItem(accessKey);
    localStorage.removeItem(refreshKey);
    localStorage.removeItem(userKey);
    setTokenState(null);
    setUserState(null);
  }, []);

  const refreshSession = useCallback(async () => {
    const currentToken = readBusinessSessionValue(accessKey);
    const storedRefreshToken = readBusinessSessionValue(refreshKey);

    if (!currentToken) {
      clearSession();
      setIsAuthReady(true);
      return null;
    }

    try {
      const currentUser = await getBusinessMe();
      sessionStorage.setItem(userKey, JSON.stringify(currentUser));
      setTokenState(currentToken);
      setUserState(currentUser);
      setIsAuthReady(true);
      return currentUser;
    } catch (error) {
      if (error.response?.status === 401 && storedRefreshToken) {
        try {
          const session = await refreshBusinessAuth(storedRefreshToken);
          setSession(session);
          setIsAuthReady(true);
          return session.user;
        } catch {
          clearSession();
        }
      } else {
        clearSession();
      }
      setIsAuthReady(true);
      return null;
    }
  }, [clearSession, setSession]);

  useEffect(() => {
    refreshSession().catch(() => {
      clearSession();
      setIsAuthReady(true);
    });
  }, [clearSession, refreshSession]);

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthReady,
      isAuthenticated: Boolean(token),
      isPlatformAdmin: user?.globalRole === "platform_admin",
      setSession,
      clearSession,
      refreshSession,
    }),
    [user, token, isAuthReady, setSession, clearSession, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
