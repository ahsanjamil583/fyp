import { createContext, useContext, useCallback, useMemo, useState } from "react";

import { getMyTenants } from "../services/tenantApi.js";

const TenantContext = createContext(null);
const selectedTenantKey = "bizxus_selected_tenant_id";

/**
 * Background refreshes re-parse the tenant from JSON, so the object is a new reference
 * even when nothing changed. Screens that key an effect on `selectedTenant` then re-run
 * and reset their form, which looked like the page reloading and losing what was typed.
 * Keeping the previous reference when the payload is identical stops that at the source.
 */
function sameSnapshot(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

export function TenantProvider({ children }) {
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);

  const selectTenant = useCallback((tenant) => {
    setSelectedTenant((current) => (sameSnapshot(current, tenant) ? current : tenant));
    if (tenant?.id) {
      localStorage.setItem(selectedTenantKey, tenant.id);
    } else {
      localStorage.removeItem(selectedTenantKey);
    }
  }, []);

  const refreshTenants = useCallback(async () => {
    setIsLoadingTenants(true);
    try {
      const data = await getMyTenants();
      setTenants((current) => (sameSnapshot(current, data) ? current : data));
      const savedId = localStorage.getItem(selectedTenantKey);
      const nextSelected = data.find((tenant) => tenant.id === savedId) || data[0] || null;
      selectTenant(nextSelected);
      return data;
    } finally {
      setIsLoadingTenants(false);
    }
  }, [selectTenant]);

  const value = useMemo(
    () => ({
      selectedTenant,
      tenants,
      isLoadingTenants,
      setTenants,
      selectTenant,
      refreshTenants,
    }),
    [selectedTenant, tenants, isLoadingTenants, selectTenant, refreshTenants],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  return useContext(TenantContext);
}
