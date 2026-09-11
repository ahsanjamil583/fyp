import { apiClient } from "./apiClient.js";

export async function getAdminOverview() {
  const response = await apiClient.get("/admin/overview");
  return response.data.data;
}

export async function getAdminReports() {
  const response = await apiClient.get("/admin/reports");
  return response.data.data;
}

export async function getAdminPayments() {
  const response = await apiClient.get("/admin/payments");
  return response.data.data;
}

export async function getAdminUsers() {
  const response = await apiClient.get("/admin/users");
  return response.data.data;
}

export async function updateAdminUser(userId, payload) {
  const response = await apiClient.put(`/admin/users/${userId}`, payload);
  return response.data.data;
}

export async function getAdminTenants() {
  const response = await apiClient.get("/admin/tenants");
  return response.data.data;
}

export async function updateAdminTenant(tenantId, payload) {
  const response = await apiClient.put(`/admin/tenants/${tenantId}`, payload);
  return response.data.data;
}

export async function decideAdminPackageRequest(tenantId, planCode, payload) {
  const response = await apiClient.post(`/admin/tenants/${tenantId}/package-requests/${planCode}/decision`, payload);
  return response.data.data;
}

export async function decideAdminWebsiteRequest(tenantId, payload) {
  const response = await apiClient.post(`/admin/tenants/${tenantId}/website-request/decision`, payload);
  return response.data.data;
}
