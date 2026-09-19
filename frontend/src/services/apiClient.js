import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

const businessAccessKey = "bizxus_business_access_token";
const businessRefreshKey = "bizxus_business_refresh_token";
const businessUserKey = "bizxus_business_user";
let businessRefreshRequest = null;

const customerAccessKey = "bizxus_customer_access_token";
const customerRefreshKey = "bizxus_customer_refresh_token";
const customerUserKey = "bizxus_customer_user";
const customerProfileKey = "bizxus_customer_profile";
let customerRefreshRequest = null;

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

/**
 * The customer equivalent of refreshBusinessAccessToken.
 *
 * Without it a customer access token simply expired after an hour: the 401 was
 * rejected, nothing cleared the stored token, and ProtectedRoute still saw a token and
 * kept the customer "logged in" on a portal where every request failed.
 */
async function refreshCustomerAccessToken() {
  const refreshToken = localStorage.getItem(customerRefreshKey);
  if (!refreshToken) {
    throw new Error("Missing customer refresh token.");
  }

  if (!customerRefreshRequest) {
    customerRefreshRequest = axios
      .post(
        `${apiClient.defaults.baseURL}/customer/auth/refresh`,
        { refreshToken },
        { headers: { "Content-Type": "application/json" } },
      )
      .then((response) => {
        const session = response.data?.data;
        if (!session?.accessToken || !session?.refreshToken) {
          throw new Error("Invalid refresh response.");
        }
        localStorage.setItem(customerAccessKey, session.accessToken);
        localStorage.setItem(customerRefreshKey, session.refreshToken);
        if (session.user) {
          localStorage.setItem(customerUserKey, JSON.stringify(session.user));
        }
        return session.accessToken;
      })
      .finally(() => {
        customerRefreshRequest = null;
      });
  }

  return customerRefreshRequest;
}

function clearCustomerSession() {
  [customerAccessKey, customerRefreshKey, customerUserKey, customerProfileKey].forEach((key) => {
    localStorage.removeItem(key);
  });
}

const PASSWORD_RESET_REQUIRED = "password_reset_required";

/**
 * Router-driven navigation for the interceptor.
 *
 * This module cannot import the router (the router imports pages, which import this
 * module), so App registers a handler instead. Falling back to window.location would
 * be a full document reload, which throws away everything the user has typed.
 */
let navigationHandler = null;

export function setApiNavigationHandler(handler) {
  navigationHandler = typeof handler === "function" ? handler : null;
}

function redirectToForcedPasswordReset(isCustomerRequest) {
  const target = isCustomerRequest ? "/customer/update-password" : "/update-password";
  if (window.location.pathname === target) {
    return;
  }
  if (navigationHandler) {
    navigationHandler(target);
    return;
  }
  window.location.assign(target);
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isBusinessRequest = !originalRequest?.url?.startsWith("/customer/");

    // The API blocks every route except the change-password one until a weak
    // legacy password is replaced. Send the user straight to that form.
    if (error.response?.status === 403 && error.response?.data?.detail === PASSWORD_RESET_REQUIRED) {
      if (!originalRequest?.url?.includes("/password/change")) {
        redirectToForcedPasswordReset(!isBusinessRequest);
      }
      return Promise.reject(error);
    }
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

    if (
      error.response?.status === 401 &&
      !isBusinessRequest &&
      !originalRequest?._retry &&
      !isAuthRefreshRequest &&
      !isAuthLoginRequest &&
      !isAuthRegisterRequest
    ) {
      originalRequest._retry = true;

      try {
        const nextAccessToken = await refreshCustomerAccessToken();
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // The session is genuinely over. Clear it and send them to login, rather than
        // leaving a dead token behind that ProtectedRoute reads as "still signed in".
        clearCustomerSession();
        if (window.location.pathname !== "/customer/login") {
          if (navigationHandler) {
            navigationHandler("/customer/login");
          } else {
            window.location.assign("/customer/login");
          }
        }
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
