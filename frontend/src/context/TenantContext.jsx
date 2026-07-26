import { createContext, useContext, useCallback, useMemo, useState } from "react";

import { getMyTenants } from "../services/tenantApi.js";

const TenantContext = createContext(null);
const selectedTenantKey = "bizxus_selected_tenant_id";

export function TenantProvider({ children }) {
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);

  const selectTenant = useCallback((tenant) => {
    setSelectedTenant(tenant);
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
      setTenants(data);
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
