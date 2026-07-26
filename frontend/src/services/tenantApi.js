import { apiClient } from "./apiClient.js";

export async function createTenant(payload) {
  const response = await apiClient.post("/tenants", payload);
  return response.data.data;
}

export async function getMyTenants() {
  const response = await apiClient.get("/tenants/my");
  return response.data.data;
}

export async function getTenant(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}`);
  return response.data.data;
}

export async function updateTenant(tenantId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}`, payload);
  return response.data.data;
}

export async function publishTenant(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/publish`);
  return response.data.data;
}

export async function unpublishTenant(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/unpublish`);
  return response.data.data;
}
