import { useEffect, useState } from "react";

import { PaymentStatusBadge } from "../../components/payments/PaymentStatusBadge.jsx";
import { getAdminPayments } from "../../services/adminApi.js";

export function AdminPaymentsPage() {
  const [data, setData] = useState({ summary: {}, records: [], stripeWebhookEvents: [] });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError("");
      try {
        setData(await getAdminPayments());
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load admin payments.");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  const summary = data.summary || {};

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Platform Payments</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Payment Monitor</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review Stripe test payments, local payment records, and webhook delivery status across all tenants.
        </p>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading payment monitor...</div> : null}

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Records" value={summary.totalPaymentRecords || 0} />
        <StatCard label="Stripe paid" value={formatMoney(summary.stripePaidAmount || 0)} />
        <StatCard label="Stripe pending" value={formatMoney(summary.stripePendingAmount || 0)} />
        <StatCard label="Paid count" value={summary.stripePaidCount || 0} />
        <StatCard label="Webhook events" value={summary.webhookEvents || 0} />
        <StatCard label="Webhook failures" value={summary.failedWebhookEvents || 0} danger={summary.failedWebhookEvents > 0} />
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-ink">Recent Payment Records</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2">Tenant</th>
                <th className="px-3 py-2">Transaction</th>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2">Amount</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Provider Ref</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(data.records || []).map((record) => (
                <tr key={record.id}>
                  <td className="px-3 py-3">
                    <div className="font-semibold text-ink">{record.tenant?.name || "Unknown"}</div>
                    <div className="text-xs text-muted">{record.tenant?.slug || "-"}</div>
                  </td>
                  <td className="px-3 py-3 font-semibold text-ink">{record.transactionNumber || "-"}</td>
                  <td className="px-3 py-3 capitalize text-muted">{String(record.method || "").replaceAll("_", " ")}</td>
                  <td className="px-3 py-3 text-muted">{formatMoney(record.amount)}</td>
                  <td className="px-3 py-3"><PaymentStatusBadge compact status={record.status} /></td>
                  <td className="px-3 py-3 text-xs text-muted">{record.providerPaymentIntentId || record.providerSessionId || record.referenceNumber || "-"}</td>
                </tr>
              ))}
              {!(data.records || []).length && !isLoading ? (
                <tr><td className="px-3 py-5 text-sm text-muted" colSpan="6">No payment records yet.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-ink">Stripe Webhook Events</h2>
        <div className="mt-4 space-y-3">
          {(data.stripeWebhookEvents || []).map((event) => (
            <div key={event.id} className="rounded-md border border-line bg-surface p-3 text-sm">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-semibold text-ink">{event.eventType || "stripe event"}</div>
                  <div className="mt-1 text-xs text-muted">{event.eventId}</div>
                  {event.error ? <div className="mt-1 text-xs text-red-700">{event.error}</div> : null}
                </div>
                <span className={event.status === "processed" ? "w-fit rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700" : event.status === "failed" ? "w-fit rounded-full bg-red-50 px-2 py-1 text-xs font-bold text-red-700" : "w-fit rounded-full bg-slate-50 px-2 py-1 text-xs font-bold text-slate-700"}>
                  {event.status || "unknown"}
                </span>
              </div>
            </div>
          ))}
          {!(data.stripeWebhookEvents || []).length && !isLoading ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No Stripe webhook events yet.</div> : null}
        </div>
      </div>
    </section>
  );
}

function StatCard({ label, value, danger = false }) {
  return (
    <div className={danger ? "rounded-md border border-red-100 bg-red-50 p-4 shadow-sm" : "rounded-md border border-line bg-white p-4 shadow-sm"}>
      <div className={danger ? "text-sm text-red-700" : "text-sm text-muted"}>{label}</div>
      <div className={danger ? "mt-2 text-2xl font-semibold text-red-800" : "mt-2 text-2xl font-semibold text-ink"}>{value}</div>
    </div>
  );
}

function formatMoney(value) {
  const number = Number(value || 0);
  return `PKR ${number.toLocaleString()}`;
}
