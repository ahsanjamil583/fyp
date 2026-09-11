const statusStyles = {
  paid: "bg-green-50 text-green-700 border-green-100",
  partially_paid: "bg-emerald-50 text-emerald-700 border-emerald-100",
  pending_verification: "bg-amber-50 text-amber-700 border-amber-100",
  pending: "bg-amber-50 text-amber-700 border-amber-100",
  cod: "bg-brand-50 text-brand-700 border-brand-100",
  unpaid: "bg-slate-50 text-slate-700 border-slate-200",
  rejected: "bg-red-50 text-red-700 border-red-100",
  failed: "bg-red-50 text-red-700 border-red-100",
  refunded: "bg-purple-50 text-purple-700 border-purple-100",
  awaiting_quote: "bg-slate-50 text-slate-700 border-slate-200",
  quoted: "bg-brand-50 text-brand-700 border-brand-100",
  not_applicable: "bg-slate-50 text-slate-500 border-slate-200",
};

export function formatPaymentStatus(status) {
  if (!status) return "Unpaid";
  return String(status)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function PaymentStatusBadge({ status, compact = false }) {
  const normalized = status || "unpaid";
  return (
    <span className={`inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${statusStyles[normalized] || statusStyles.unpaid}`}>
      {compact ? formatPaymentStatus(normalized).replace("Pending Verification", "Review") : formatPaymentStatus(normalized)}
    </span>
  );
}

export function PaymentProofBadge({ summary }) {
  if (!summary) return null;
  if (summary.hasPendingProof) {
    return <span className="inline-flex w-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">Proof waiting for owner review</span>;
  }
  if (summary.hasRejectedProof && !summary.hasApprovedPayment) {
    return <span className="inline-flex w-fit rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700">Proof rejected, resubmit needed</span>;
  }
  if (summary.hasApprovedPayment) {
    return <span className="inline-flex w-fit rounded-full bg-green-50 px-2.5 py-1 text-xs font-semibold text-green-700">Payment verified</span>;
  }
  return null;
}

export function PaymentLifecycleNote({ transaction }) {
  const summary = transaction?.paymentProofSummary;
  if (summary?.hasPendingProof) {
    return "Customer proof is waiting for owner approval.";
  }
  if (summary?.hasRejectedProof && !summary?.hasApprovedPayment) {
    return "Latest proof was rejected. Customer should submit a corrected reference or screenshot.";
  }
  if (transaction?.paymentPreference?.methodLabel) {
    return `Preferred method: ${transaction.paymentPreference.methodLabel}.`;
  }
  return "";
}
