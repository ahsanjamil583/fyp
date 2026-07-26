export function formatApiError(detail, fallbackMessage = "Something went wrong.") {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const key = item.key ? `${item.key}: ` : "";
          const message = item.message || JSON.stringify(item);
          return `${key}${message}`;
        }
        return String(item);
      })
      .join(" ");
  }

  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") {
      return detail.message;
    }
    return JSON.stringify(detail);
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  return fallbackMessage;
}
