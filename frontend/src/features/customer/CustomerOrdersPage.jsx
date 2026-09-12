import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, PackageCheck } from "lucide-react";

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
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Orders</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Orders & payments</h1>
        <p className="mt-3 text-sm text-muted">{meta.total || 0} orders found. Open an order to pay, upload proof, view receipts, or reorder.</p>
      </div>
      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      <div className="grid gap-3 lg:hidden">
        {orders.map((order) => (
          <article key={order.id} className="rounded-xl border border-line bg-white p-4 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link className="font-bold text-ink hover:text-brand" to={`/customer/orders/${order.id}`}>{order.transactionNumber}</Link>
                <div className="mt-1 text-xs text-muted">{new Date(order.createdAt).toLocaleString()}</div>
              </div>
              <PaymentStatusBadge compact status={order.paymentStatus} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-surface px-3 py-2">
                <div className="text-xs text-muted">Status</div>
                <div className="font-semibold capitalize text-ink">{order.status}</div>
              </div>
              <div className="rounded-lg bg-surface px-3 py-2">
                <div className="text-xs text-muted">Total</div>
                <div className="font-semibold text-ink">{order.pricing?.total}</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link className="ui-btn-secondary !py-2" to={`/customer/orders/${order.id}`}>
                {["unpaid", "rejected", "pending_verification"].includes(order.paymentStatus) ? "Pay / proof" : "View order"}
                <ArrowRight size={14} />
              </Link>
              <button
                type="button"
                className="ui-btn-secondary !py-2"
                onClick={async () => {
                  const result = await reorderCustomerTransaction(order.id);
                  setMessage(`Items from ${order.transactionNumber} were added to your cart for ${result.tenantSlug}.`);
                }}
              >
                Reorder
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-hidden rounded-xl border border-line bg-white shadow-card lg:block">
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
          </tbody>
        </table>
      </div>
      {!orders.length ? (
        <div className="rounded-xl border border-dashed border-line bg-surface p-8 text-center">
          <PackageCheck className="mx-auto text-brand" size={30} />
          <div className="mt-3 font-bold text-ink">No orders yet</div>
          <p className="mt-1 text-sm text-muted">Start from the marketplace, add items to cart, then place your first order.</p>
          <Link className="ui-btn-primary mt-5" to="/customer/marketplace">
            Browse businesses
          </Link>
        </div>
      ) : null}
    </section>
  );
}
