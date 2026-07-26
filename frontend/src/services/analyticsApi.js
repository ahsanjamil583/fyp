import { apiClient } from "./apiClient.js";

export async function getAnalyticsSummary(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/analytics/summary`);
  return response.data.data;
}
