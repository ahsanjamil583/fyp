import { apiClient } from "./apiClient.js";

export async function getOwnerConversations(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/ai/conversations`);
  return response.data.data;
}

export async function getOwnerConversationDetail(tenantId, conversationId) {
  const response = await apiClient.get(`/tenants/${tenantId}/ai/conversations/${conversationId}`);
  return response.data.data;
}

export async function getTenantRagStatus(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/ai/rag/status`);
  return response.data.data;
}

export async function reindexTenantRag(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/ai/rag/reindex`);
  return response.data.data;
}
