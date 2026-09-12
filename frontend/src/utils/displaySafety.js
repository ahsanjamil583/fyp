/**
 * Guards for anything technical that must not reach a normal user's screen.
 *
 * Pages were rendering agent/tool traces, raw JSON, bridge URLs and environment
 * blocks straight into the UI. Those are developer aids, so they now sit behind an
 * explicit flag, and every value that reaches JSX goes through a formatter that
 * cannot produce "[object Object]".
 */

/**
 * Developer surfaces: strictly opt-in via VITE_SHOW_DEBUG_PANEL=true.
 *
 * This deliberately does NOT include `import.meta.env.DEV`. That flag is true for the
 * whole of `npm run dev`, which is how the app is normally used and demoed, so keying
 * off it left every trace, env block and internal URL on screen for real users.
 */
export const isDebugMode = String(import.meta.env.VITE_SHOW_DEBUG_PANEL || "") === "true";

/** Anything matching these reads as internal plumbing rather than user information. */
const SECRET_KEY = /(token|secret|password|hash|grant|salt|credential|apikey|api_key|authorization)/i;

/**
 * Render-safe string for an arbitrary API value.
 * Objects and arrays are summarised rather than stringified, so `[object Object]`
 * can never appear.
 */
export function formatDisplayValue(value, { fallback = "—" } = {}) {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const parts = value.map((entry) => formatDisplayValue(entry, { fallback: "" })).filter(Boolean);
    return parts.length ? parts.join(", ") : fallback;
  }
  if (typeof value === "object") {
    // Prefer a human-meaningful field before giving up on the object.
    for (const key of ["label", "name", "title", "displayName", "text", "message", "value"]) {
      if (typeof value[key] === "string" && value[key].trim()) return value[key];
    }
    const count = Object.keys(value).length;
    return count ? `${count} item${count === 1 ? "" : "s"}` : fallback;
  }
  return fallback;
}

/** Drops secret-ish keys from an object before it is shown anywhere. */
export function withoutSecrets(source) {
  if (!source || typeof source !== "object") return source;
  return Object.fromEntries(Object.entries(source).filter(([key]) => !SECRET_KEY.test(key)));
}

/** Turns `orchestrator_agent` / `catalog_lookup` into "Orchestrator agent" for rare owner-facing copy. */
export function humanizeInternalName(name) {
  if (!name) return "";
  return String(name)
    .replaceAll("_", " ")
    .replace(/\b\w/, (c) => c.toUpperCase());
}

/** Owner-friendly wording for the model/source that produced an answer. */
const SOURCE_LABELS = {
  live_catalog: "Live catalog",
  rag: "Business knowledge",
  knowledge_base: "Business knowledge",
  rule_based: "Standard reply",
  openai: "AI assistant",
  groq: "AI assistant",
  fallback: "Standard reply",
};

export function formatAnswerSource(source) {
  if (!source) return "";
  return SOURCE_LABELS[String(source).toLowerCase()] || "AI assistant";
}

const GENERIC_SOURCE_TITLES = new Set([
  "style",
  "system",
  "prompt",
  "instructions",
  "safety",
  "policy",
  "configuration",
  "category",
]);

export function getUserFacingSourceTitles(sources = []) {
  const titles = sources
    .map((source) => (typeof source?.title === "string" ? source.title.trim() : ""))
    .filter((title) => title.length > 2 && !GENERIC_SOURCE_TITLES.has(title.toLowerCase()));
  return [...new Set(titles)];
}
