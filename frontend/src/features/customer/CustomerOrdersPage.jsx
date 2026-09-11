import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PaymentProofBadge, PaymentStatusBadge } from "../../components/payments/PaymentStatusBadge.jsx";
import { getCustomerTransactions, reorderCustomerTransaction } from "../../services/customerPortalApi.js";
import { formatTransactionType } from "../../utils/transaction.js";

export function CustomerOrdersPage() {
  const [orders, setOrders] = useState([]);
  const [meta, setMeta] = useState({});
  const [message, setMessage] = useState("");

  useEffect(() => {
    getCustomerTransactions({ page: 1, limit: 20 }).then((result) => {
      setOrders(result.items);
      setMeta(result.meta);
    });
  }, []);

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Transactions</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Transaction History</h1>
        <p className="mt-3 text-sm text-muted">{meta.total || 0} transactions found.</p>
      </div>
      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      <div className="rounded-xl border border-line bg-white shadow-card">
        <table className="min-w-full divide-y divide-line text-sm">
          <thead className="bg-surface">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-ink">Transaction</th>
              <th className="px-4 py-3 text-left font-semibold text-ink">Type</th>
              <th className="px-4 py-3 text-left font-semibold text-ink">Status</th>
              <th className="px-4 py-3 text-left font-semibold text-ink">Payment</th>
              <th className="px-4 py-3 text-left font-semibold text-ink">Total</th>
              <th className="px-4 py-3 text-left font-semibold text-ink">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line bg-white">
            {orders.map((order) => (
              <tr key={order.id}>
                <td className="px-4 py-3">
                  <Link className="font-semibold text-ink hover:text-brand" to={`/customer/orders/${order.id}`}>{order.transactionNumber}</Link>
                  <div className="text-xs text-muted">{new Date(order.createdAt).toLocaleString()}</div>
                </td>
                <td className="px-4 py-3 capitalize text-muted">{formatTransactionType(order.transactionType)}</td>
                <td className="px-4 py-3 capitalize text-muted">{order.status}</td>
                <td className="px-4 py-3">
                  <div className="space-y-1.5">
                    <PaymentStatusBadge compact status={order.paymentStatus} />
                    <PaymentProofBadge summary={order.paymentProofSummary} />
                    {order.paymentPreference?.methodLabel ? <div className="text-xs text-muted">{order.paymentPreference.methodLabel}</div> : null}
                  </div>
                </td>
                <td className="px-4 py-3 text-muted">{order.pricing?.total}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Link className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" to={`/customer/orders/${order.id}`}>
                      {["unpaid", "rejected", "pending_verification"].includes(order.paymentStatus) ? "View payment" : "View"}
                    </Link>
                    <button
                      className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink"
                      onClick={async () => {
                        const result = await reorderCustomerTransaction(order.id);
                        setMessage(`Items from ${order.transactionNumber} were added to your cart for ${result.tenantSlug}.`);
                      }}
                    >
                      Reorder
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!orders.length ? (
              <tr>
                <td className="px-4 py-5 text-sm text-muted" colSpan="6">No transactions yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
