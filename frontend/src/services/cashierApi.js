import { apiClient } from "./apiClient.js";

/* ------------------------------------------------------ owner: manage staff -- */

export async function getTenantCashiers(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/cashiers`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function createTenantCashier(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/cashiers`, payload);
  return response.data.data;
}

export async function updateTenantCashier(tenantId, cashierId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/cashiers/${cashierId}`, payload);
  return response.data.data;
}

export async function setTenantCashierStatus(tenantId, cashierId, isActive) {
  const response = await apiClient.post(`/tenants/${tenantId}/cashiers/${cashierId}/status`, { isActive });
  return response.data.data;
}

export async function resetTenantCashierPassword(tenantId, cashierId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/cashiers/${cashierId}/password`, payload);
  return response.data.data;
}

export async function removeTenantCashier(tenantId, cashierId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/cashiers/${cashierId}`);
  return response.data.data;
}

/* --------------------------------------------------- cashier: own workspace -- */

export async function getCashierProfile() {
  const response = await apiClient.get("/cashier/me");
  return response.data.data;
}

export async function getCashierDashboard() {
  const response = await apiClient.get("/cashier/dashboard");
  return response.data.data;
}

export async function getCashierCatalog(params = {}) {
  const response = await apiClient.get("/cashier/catalog", { params });
  return response.data.data;
}

export async function getCashierOrders(params = {}) {
  const response = await apiClient.get("/cashier/orders", { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function checkCashierOrder(payload) {
  const response = await apiClient.post("/cashier/orders/check", payload);
  return response.data.data;
}

export async function createCashierOrder(payload) {
  const response = await apiClient.post("/cashier/orders", payload);
  return response.data.data;
}

export async function getCashierReceipt(receiptToken) {
  const response = await apiClient.get(`/cashier/receipts/${receiptToken}`);
  return response.data.data;
}
