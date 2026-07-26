import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { getCustomerMe } from "../services/customerAuthApi.js";

const CustomerContext = createContext(null);
const accessKey = "bizxus_customer_access_token";
const refreshKey = "bizxus_customer_refresh_token";
const userKey = "bizxus_customer_user";
const profileKey = "bizxus_customer_profile";

export function CustomerProvider({ children }) {
  const [customer, setCustomerState] = useState(() => {
    const saved = localStorage.getItem(userKey);
    return saved ? JSON.parse(saved) : null;
  });
  const [customerProfile, setCustomerProfileState] = useState(() => {
    const saved = localStorage.getItem(profileKey);
    return saved ? JSON.parse(saved) : null;
  });
  const [customerToken, setCustomerTokenState] = useState(() => localStorage.getItem(accessKey));

  function setCustomerSession(session) {
    localStorage.setItem(accessKey, session.accessToken);
    localStorage.setItem(refreshKey, session.refreshToken);
    localStorage.setItem(userKey, JSON.stringify(session.user));
    setCustomerTokenState(session.accessToken);
    setCustomerState(session.user);
    if (session.profile) {
      localStorage.setItem(profileKey, JSON.stringify(session.profile));
      setCustomerProfileState(session.profile);
    }
  }

  function clearCustomerSession() {
    localStorage.removeItem(accessKey);
    localStorage.removeItem(refreshKey);
    localStorage.removeItem(userKey);
    localStorage.removeItem(profileKey);
    setCustomerTokenState(null);
    setCustomerState(null);
    setCustomerProfileState(null);
  }

  const refreshCustomerMe = useCallback(async () => {
    const data = await getCustomerMe();
    localStorage.setItem(userKey, JSON.stringify(data.user));
    localStorage.setItem(profileKey, JSON.stringify(data.profile));
    setCustomerState(data.user);
    setCustomerProfileState(data.profile);
    return data;
  }, []);

  const value = useMemo(
    () => ({
      customer,
      customerProfile,
      customerToken,
      isCustomerAuthenticated: Boolean(customerToken),
      setCustomerSession,
      clearCustomerSession,
      refreshCustomerMe,
    }),
    [customer, customerProfile, customerToken],
  );

  return <CustomerContext.Provider value={value}>{children}</CustomerContext.Provider>;
}

export function useCustomer() {
  return useContext(CustomerContext);
}
