import { apiClient } from "./apiClient.js";

export async function getModules() {
  const response = await apiClient.get("/modules");
  return response.data.data;
}

export async function getAdminModules() {
  const response = await apiClient.get("/admin/modules");
  return response.data.data;
}

export async function createAdminModule(payload) {
  const response = await apiClient.post("/admin/modules", payload);
  return response.data.data;
}

export async function updateAdminModule(moduleCode, payload) {
  const response = await apiClient.put(`/admin/modules/${moduleCode}`, payload);
  return response.data.data;
}

export async function getTenantModules(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/modules`);
  return response.data.data;
}

export async function enableTenantModule(tenantId, moduleCode) {
  const response = await apiClient.post(`/tenants/${tenantId}/modules/${moduleCode}/enable`);
  return response.data.data;
}

export async function disableTenantModule(tenantId, moduleCode) {
  const response = await apiClient.post(`/tenants/${tenantId}/modules/${moduleCode}/disable`);
  return response.data.data;
}

export async function updateTenantModuleConfig(tenantId, moduleCode, config) {
  const response = await apiClient.put(`/tenants/${tenantId}/modules/${moduleCode}/config`, { config });
  return response.data.data;
}
