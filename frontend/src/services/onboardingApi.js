import { apiClient } from "./apiClient.js";

export async function getLaunchStatus(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/launch/status`);
  return response.data.data;
}

export async function applyLaunchProfile(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/launch/apply-profile`, payload);
  return response.data.data;
}

export async function requestPackageUpgrade(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/launch/request-upgrade`, payload);
  return response.data.data;
}

export async function finalizeLaunch(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/launch/finalize`, payload);
  return response.data.data;
}
