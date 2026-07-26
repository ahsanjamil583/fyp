import { createContext, useContext, useCallback, useMemo, useState } from "react";

import { getTenantModules } from "../services/moduleApi.js";

const ModuleContext = createContext(null);

export function ModuleProvider({ children }) {
  const [enabledModules, setEnabledModules] = useState([]);
  const [tenantModules, setTenantModules] = useState([]);
  const [tenantPlan, setTenantPlan] = useState(null);
  const [availablePlans, setAvailablePlans] = useState([]);
  const [isLoadingModules, setIsLoadingModules] = useState(false);

  const refreshTenantModules = useCallback(async (tenantId) => {
    if (!tenantId) {
      setTenantModules([]);
      setEnabledModules([]);
      return null;
    }
    setIsLoadingModules(true);
    try {
      const data = await getTenantModules(tenantId);
      setTenantModules(data.modules);
      setEnabledModules(data.tenant.enabledModuleCodes || []);
      setTenantPlan(data.tenantPlan || null);
      setAvailablePlans(data.plans || []);
      return data;
    } finally {
      setIsLoadingModules(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      enabledModules,
      setEnabledModules,
      tenantModules,
      setTenantModules,
      tenantPlan,
      availablePlans,
      isLoadingModules,
      refreshTenantModules,
      hasModule: (moduleCode) => enabledModules.includes(moduleCode),
    }),
    [enabledModules, tenantModules, tenantPlan, availablePlans, isLoadingModules, refreshTenantModules],
  );

  return <ModuleContext.Provider value={value}>{children}</ModuleContext.Provider>;
}

export function useModules() {
  return useContext(ModuleContext);
}
