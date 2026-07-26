import { apiClient } from "./apiClient.js";

export async function getFinalQaChecklist(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/qa/checklist`);
  return response.data.data;
}

export async function recordFinalQaDemoRun(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/qa/demo-run`, payload);
  return response.data.data;
}
