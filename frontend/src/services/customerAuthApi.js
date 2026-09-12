import { apiClient } from "./apiClient.js";

export async function registerCustomer(payload) {
  const response = await apiClient.post("/customer/auth/register", payload);
  return response.data.data;
}

export async function requestCustomerEmailOtp(payload) {
  const response = await apiClient.post("/customer/auth/otp/email/request", payload);
  return response.data.data;
}

export async function verifyCustomerEmailOtp(payload) {
  const response = await apiClient.post("/customer/auth/otp/email/verify", payload);
  return response.data.data;
}

export async function loginCustomer(payload) {
  const response = await apiClient.post("/customer/auth/login", payload);
  return response.data.data;
}

export async function requestCustomerOtp(payload) {
  const response = await apiClient.post("/customer/auth/otp/request", payload);
  return response.data.data;
}

export async function verifyCustomerOtp(payload) {
  const response = await apiClient.post("/customer/auth/otp/verify", payload);
  return response.data.data;
}

export async function requestCustomerEmailPasswordResetOtp(payload) {
  const response = await apiClient.post("/customer/auth/password/email/request", payload);
  return response.data.data;
}

export async function resetCustomerPasswordWithEmailOtp(payload) {
  const response = await apiClient.post("/customer/auth/password/email/reset", payload);
  return response.data.data;
}

export async function changeCustomerPassword(payload) {
  const response = await apiClient.post("/customer/auth/password/change", payload);
  return response.data.data;
}

export async function getCustomerMe() {
  const response = await apiClient.get("/customer/auth/me");
  return response.data.data;
}

export async function logoutCustomer() {
  const response = await apiClient.post("/customer/auth/logout");
  return response.data;
}

export async function updateCustomerProfile(payload) {
  const response = await apiClient.put("/customer/auth/profile", payload);
  return response.data.data;
}
