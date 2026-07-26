import { apiClient } from "./apiClient.js";

export async function getTenantTransactions(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/transactions`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function updateTenantTransaction(tenantId, transactionId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/transactions/${transactionId}`, payload);
  return response.data.data;
}
