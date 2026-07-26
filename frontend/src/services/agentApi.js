import { apiClient } from "./apiClient.js";

export async function getAgentTools(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/agent/tools`);
  return response.data.data;
}

export async function previewAgentRun(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/agent/preview`, payload);
  return response.data.data;
}
