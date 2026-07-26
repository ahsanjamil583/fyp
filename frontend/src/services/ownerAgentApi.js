import { apiClient } from "./apiClient.js";

export async function getOwnerAgentInsights(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/owner-agent/insights`);
  return response.data.data;
}

export async function sendOwnerAgentMessage(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/owner-agent/chat`, payload);
  return response.data.data;
}

export async function getOwnerAgentHistory(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/owner-agent/history`, { params });
  return { items: response.data.data, meta: response.data.meta };
}
