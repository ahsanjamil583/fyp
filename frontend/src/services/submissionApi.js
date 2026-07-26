import { apiClient } from "./apiClient.js";

export async function getSubmissionPackage(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/submission/package`);
  return response.data.data;
}

export async function getSubmissionExport(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/submission/export`);
  return response.data.data;
}

export async function recordSubmissionSignoff(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/submission/signoff`, payload);
  return response.data.data;
}
