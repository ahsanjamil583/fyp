import { apiClient } from "./apiClient.js";

export async function registerCustomer(payload) {
  const response = await apiClient.post("/customer/auth/register", payload);
  return response.data.data;
}

export async function registerCustomerWithPhone(payload) {
  const response = await apiClient.post("/customer/auth/register/phone", payload);
  return response.data.data;
}

export async function loginCustomer(payload) {
  const response = await apiClient.post("/customer/auth/login", payload);
  return response.data.data;
}

export async function loginCustomerWithPhone(payload) {
  const response = await apiClient.post("/customer/auth/login/phone", payload);
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

export async function requestCustomerPasswordResetOtp(payload) {
  const response = await apiClient.post("/customer/auth/password/phone/request", payload);
  return response.data.data;
}

export async function resetCustomerPasswordWithOtp(payload) {
  const response = await apiClient.post("/customer/auth/password/phone/reset", payload);
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
