import { apiClient } from "./apiClient.js";

export async function getReadinessReport() {
  const response = await apiClient.get("/health/readiness");
  return response.data.data;
}

export async function getDemoAccounts() {
  const response = await apiClient.get("/health/demo-accounts");
  return response.data.data;
}
