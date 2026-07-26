export const transactionTypeOptions = [
  { value: "auto", label: "Auto detect" },
  { value: "order", label: "Order" },
  { value: "quote_request", label: "Quote request" },
  { value: "booking_request", label: "Booking request" },
  { value: "inquiry", label: "Inquiry" },
];

export function formatTransactionType(value) {
  if (!value) return "transaction";
  return value.replaceAll("_", " ");
}

export function formatTransactionLabel(value) {
  const normalized = value || "transaction";
  if (normalized === "quote_request") return "quote request";
  if (normalized === "booking_request") return "booking request";
  return normalized.replaceAll("_", " ");
}

export function formatTransactionSuccess(transaction) {
  const label = formatTransactionLabel(transaction?.transactionType);
  const total = transaction?.pricing?.total;
  return total ? `${capitalize(label)} ${transaction.transactionNumber} submitted. Total: ${total}` : `${capitalize(label)} ${transaction.transactionNumber} submitted.`;
}

export function capitalize(value) {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}
