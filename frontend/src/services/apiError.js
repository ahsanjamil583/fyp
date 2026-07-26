export function getApiErrorMessage(error, fallback = "Request failed.") {
  const data = error?.response?.data;

  if (typeof data?.detail === "string" && data.detail.trim()) {
    return data.detail;
  }

  if (Array.isArray(data?.detail)) {
    const firstDetail = data.detail.find((item) => item && (item.msg || item.message || item.detail));
    if (firstDetail) {
      return firstDetail.msg || firstDetail.message || firstDetail.detail || fallback;
    }
  }

  if (typeof data?.message === "string" && data.message.trim()) {
    return data.message;
  }

  if (typeof data?.error?.message === "string" && data.error.message.trim()) {
    return data.error.message;
  }

  if (Array.isArray(data?.error?.details)) {
    const firstDetail = data.error.details.find((item) => item && (item.message || item.detail || item.msg));
    if (firstDetail) {
      return firstDetail.message || firstDetail.detail || firstDetail.msg || fallback;
    }
  }

  if (error?.code === "ERR_NETWORK" || error?.message === "Network Error") {
    return "Unable to reach the API server. Please check that the backend is running.";
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message;
  }

  return fallback;
}
