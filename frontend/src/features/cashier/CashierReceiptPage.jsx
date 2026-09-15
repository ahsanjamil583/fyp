import { ArrowLeft, CheckCircle2, Printer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Alert } from "../../components/ui/index.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCashierReceipt } from "../../services/cashierApi.js";
import { formatMoney, formatOrderTime } from "./cashierShared.jsx";
import { resolveUploadUrl } from "../../services/itemApi.js";

/**
 * The printed artefact.
 *
 * The receipt body is sized like thermal paper (80mm) and carries its own print rules:
 * `print-hide` removes the navigation and the action bar, and `receipt-sheet` drops the
 * card chrome so the page that leaves the printer is the receipt and nothing else. The
 * same markup is what the cashier sees on screen, so there is no second layout that can
 * silently drift out of step with what customers are handed.
 */

export function CashierReceiptPage() {
  const { receiptToken } = useParams();
  const [searchParams] = useSearchParams();
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  const justCreated = searchParams.get("created") === "1";

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getCashierReceipt(receiptToken)
      .then((data) => {
        if (!cancelled) {
          setReceipt(data);
          setError("");
        }
      })
      .catch((requestError) => {
        if (!cancelled) setError(getApiErrorMessage(requestError, "That receipt could not be found."));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [receiptToken]);

  if (isLoading) {
    return <div className="py-10 text-center text-sm text-muted">Loading receipt...</div>;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Alert tone="red">{error}</Alert>
        <Link to="/cashier/orders" className="ui-btn-secondary">
          <ArrowLeft size={16} />
          Back to orders
        </Link>
      </div>
    );
  }

  const business = receipt.business || {};
  const order = receipt.order || {};
  const pricing = order.pricing || {};
  const currency = business.currency || "PKR";
  const isPaid = order.paymentStatus === "paid";

  return (
    <section className="space-y-5">
      <div className="print-hide flex flex-wrap items-center justify-between gap-3">
        <Link to="/cashier/orders" className="ui-btn-secondary">
          <ArrowLeft size={16} />
          Back to orders
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/cashier/orders/new" className="ui-btn-secondary">
            Next order
          </Link>
          <button type="button" className="ui-btn-primary px-6 py-3" onClick={() => window.print()}>
            <Printer size={18} />
            Print receipt
          </button>
        </div>
      </div>

      {justCreated ? (
        <div className="print-hide flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-bold text-green-700">
          <CheckCircle2 size={18} />
          Order saved. It is already in the business order list.
        </div>
      ) : null}

      <div className="receipt-sheet mx-auto w-full max-w-[420px] rounded-card border border-line bg-white p-6 shadow-card">
        <header className="text-center">
          {business.logoUrl ? (
            <img
              src={resolveUploadUrl(business.logoUrl)}
              alt=""
              className="mx-auto mb-3 h-16 w-16 rounded-xl object-contain"
            />
          ) : null}
          <h1 className="text-lg font-extrabold uppercase tracking-wide text-ink">{business.name}</h1>
          {business.addressLine ? <p className="mt-1 text-xs text-muted">{business.addressLine}</p> : null}
          {business.phone ? <p className="text-xs text-muted">{business.phone}</p> : null}
        </header>

        <div className="my-4 border-y border-dashed border-line py-3 text-xs text-muted">
          <ReceiptRow label="Receipt" value={order.transactionNumber} strong />
          <ReceiptRow label="Date" value={formatOrderTime(order.createdAt)} />
          <ReceiptRow label="Cashier" value={receipt.servedBy || "-"} />
          {order.customerSnapshot?.name ? <ReceiptRow label="Customer" value={order.customerSnapshot.name} /> : null}
          {order.customerSnapshot?.phone ? <ReceiptRow label="Phone" value={order.customerSnapshot.phone} /> : null}
          {order.fulfillment?.serviceType ? (
            <ReceiptRow label="Type" value={String(order.fulfillment.serviceType).replaceAll("_", " ")} />
          ) : null}
        </div>

        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line text-left text-[10px] uppercase tracking-wider text-subtle">
              <th className="pb-1.5 font-bold">Item</th>
              <th className="pb-1.5 text-center font-bold">Qty</th>
              <th className="pb-1.5 text-right font-bold">Rate</th>
              <th className="pb-1.5 text-right font-bold">Amount</th>
            </tr>
          </thead>
          <tbody>
            {(order.items || []).map((line, index) => (
              <tr key={`${line.name}-${index}`} className="border-b border-line-soft last:border-0">
                <td className="py-1.5 pr-2 font-semibold text-ink">{line.name}</td>
                <td className="py-1.5 text-center text-muted">{line.quantity}</td>
                <td className="py-1.5 text-right text-muted">{Number(line.unitPrice || 0).toFixed(2)}</td>
                <td className="py-1.5 text-right font-semibold text-ink">{Number(line.subtotal || 0).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="mt-4 space-y-1 border-t border-dashed border-line pt-3 text-xs">
          <ReceiptRow label="Subtotal" value={formatMoney(pricing.subtotal, currency)} />
          {pricing.discount ? <ReceiptRow label="Discount" value={`- ${formatMoney(pricing.discount, currency)}`} /> : null}
          {pricing.tax ? <ReceiptRow label="Tax" value={formatMoney(pricing.tax, currency)} /> : null}
          {pricing.serviceCharge ? <ReceiptRow label="Service charge" value={formatMoney(pricing.serviceCharge, currency)} /> : null}
          {pricing.deliveryFee ? <ReceiptRow label="Delivery" value={formatMoney(pricing.deliveryFee, currency)} /> : null}
          <div className="flex items-center justify-between border-t border-line pt-2 text-base font-extrabold text-ink">
            <span>Total</span>
            <span>{formatMoney(pricing.total, currency)}</span>
          </div>
          <ReceiptRow label="Payment" value={order.payment?.methodLabel || "-"} />
          {order.payment?.amountReceived ? <ReceiptRow label="Received" value={formatMoney(order.payment.amountReceived, currency)} /> : null}
          {order.payment?.changeDue ? <ReceiptRow label="Change" value={formatMoney(order.payment.changeDue, currency)} /> : null}
        </dl>

        <div className="mt-4 text-center">
          <span
            className={`inline-flex rounded-full px-4 py-1.5 text-xs font-extrabold uppercase tracking-wider ${
              isPaid ? "bg-green-50 text-green-700" : "bg-orange-100 text-orange-700"
            }`}
          >
            {isPaid ? "Paid" : "Payment pending"}
          </span>
        </div>

        {order.notes ? <p className="mt-3 text-center text-[11px] text-muted">{order.notes}</p> : null}
        <p className="mt-4 border-t border-dashed border-line pt-3 text-center text-[11px] font-semibold text-muted">
          {business.footerMessage}
        </p>
      </div>
    </section>
  );
}

function ReceiptRow({ label, value, strong = false }) {
  return (
    <div className="flex items-center justify-between gap-3 py-0.5">
      <dt className="shrink-0">{label}</dt>
      <dd className={`truncate text-right ${strong ? "font-extrabold text-ink" : "font-semibold text-ink"}`}>{value}</dd>
    </div>
  );
}
