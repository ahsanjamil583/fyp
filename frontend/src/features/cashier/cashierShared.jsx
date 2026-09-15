/**
 * Small formatting helpers the cashier screens share.
 *
 * They live here rather than in each page so a receipt, the order list and the dashboard
 * can never disagree about how an amount or a status is written - which on a printed
 * receipt would be a customer-facing bug.
 */

export function formatMoney(value, currency = "PKR") {
  const amount = Number(value || 0);
  return `${currency} ${amount.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatOrderTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("en-PK", { dateStyle: "medium", timeStyle: "short" });
}

export function orderStatusTone(status) {
  if (status === "completed") return "green";
  if (status === "cancelled") return "red";
  if (status === "pending") return "orange";
  return "blue";
}

export function paymentStatusTone(status) {
  if (status === "paid") return "green";
  if (status === "unpaid") return "orange";
  if (status === "refunded" || status === "rejected") return "red";
  return "blue";
}

const PILL_TONES = {
  green: "bg-green-50 text-green-700",
  orange: "bg-orange-100 text-orange-700",
  red: "bg-red-50 text-red-600",
  blue: "bg-blue-50 text-blue-600",
  slate: "bg-surface text-muted",
};

export function StatusPill({ tone = "slate", children }) {
  return (
    <span className={`inline-flex w-fit items-center rounded-full px-2.5 py-1 text-[11px] font-bold capitalize ${PILL_TONES[tone] || PILL_TONES.slate}`}>
      {children}
    </span>
  );
}
