import { formatDisplayValue, withoutSecrets } from "./displaySafety.js";

export function formatApiError(detail, fallbackMessage = "Something went wrong.") {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const key = item.key ? `${item.key}: ` : "";
          const message = item.message || formatDisplayValue(withoutSecrets(item), { fallback: fallbackMessage });
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
    return formatDisplayValue(withoutSecrets(detail), { fallback: fallbackMessage });
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  return fallbackMessage;
}
