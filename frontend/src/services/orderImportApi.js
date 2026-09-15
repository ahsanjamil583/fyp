import { apiClient } from "./apiClient.js";

export async function getOrderImportColumns(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/transactions/imports/columns`);
  return response.data.data;
}

export async function previewOrderImport(tenantId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post(`/tenants/${tenantId}/transactions/imports/preview`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export async function confirmOrderImport(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/transactions/imports/confirm`, payload);
  return response.data.data;
}

export async function getOrderImportHistory(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/transactions/imports`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

/**
 * The error report is a file download, so it is fetched as a blob and handed to the
 * browser rather than linked directly: the endpoint needs the Authorization header that
 * only the API client carries.
 */
export async function downloadOrderImportErrors(tenantId, importId, fileName = "import-errors.csv") {
  const response = await apiClient.get(`/tenants/${tenantId}/transactions/imports/${importId}/errors.csv`, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
