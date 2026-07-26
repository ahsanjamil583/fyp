import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

const businessAccessKey = "bizxus_business_access_token";
const businessRefreshKey = "bizxus_business_refresh_token";
const businessUserKey = "bizxus_business_user";
let businessRefreshRequest = null;

function getBusinessSessionValue(key) {
  const sessionValue = sessionStorage.getItem(key);
  if (sessionValue) {
    return sessionValue;
  }

  const legacyValue = localStorage.getItem(key);
  if (legacyValue) {
    sessionStorage.setItem(key, legacyValue);
    localStorage.removeItem(key);
    return legacyValue;
  }

  return null;
}

apiClient.interceptors.request.use((config) => {
  const customerToken = localStorage.getItem("bizxus_customer_access_token");
  const businessToken = getBusinessSessionValue(businessAccessKey);
  const token = config.url?.startsWith("/customer/") ? customerToken : businessToken;

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

async function refreshBusinessAccessToken() {
  const refreshToken = getBusinessSessionValue(businessRefreshKey);
  if (!refreshToken) {
    throw new Error("Missing business refresh token.");
  }

  if (!businessRefreshRequest) {
    businessRefreshRequest = axios
      .post(
        `${apiClient.defaults.baseURL}/auth/refresh`,
        { refreshToken },
        { headers: { "Content-Type": "application/json" } },
      )
      .then((response) => {
        const session = response.data?.data;
        if (!session?.accessToken || !session?.refreshToken || !session?.user) {
          throw new Error("Invalid refresh response.");
        }
        sessionStorage.setItem(businessAccessKey, session.accessToken);
        sessionStorage.setItem(businessRefreshKey, session.refreshToken);
        sessionStorage.setItem(businessUserKey, JSON.stringify(session.user));
        localStorage.removeItem(businessAccessKey);
        localStorage.removeItem(businessRefreshKey);
        localStorage.removeItem(businessUserKey);
        return session.accessToken;
      })
      .finally(() => {
        businessRefreshRequest = null;
      });
  }

  return businessRefreshRequest;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isBusinessRequest = !originalRequest?.url?.startsWith("/customer/");
    const isAuthRefreshRequest = originalRequest?.url?.includes("/auth/refresh");
    const isAuthLoginRequest = originalRequest?.url?.includes("/auth/login");
    const isAuthRegisterRequest = originalRequest?.url?.includes("/auth/register");

    if (
      error.response?.status === 401 &&
      isBusinessRequest &&
      !originalRequest?._retry &&
      !isAuthRefreshRequest &&
      !isAuthLoginRequest &&
      !isAuthRegisterRequest
    ) {
      originalRequest._retry = true;

      try {
        const nextAccessToken = await refreshBusinessAccessToken();
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        sessionStorage.removeItem(businessAccessKey);
        sessionStorage.removeItem(businessRefreshKey);
        sessionStorage.removeItem(businessUserKey);
        localStorage.removeItem(businessAccessKey);
        localStorage.removeItem(businessRefreshKey);
        localStorage.removeItem(businessUserKey);
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);

export async function getHealth() {
  const response = await apiClient.get("/health");
  return response.data;
}
