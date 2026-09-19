import { AlertCircle, CheckCircle2, ShoppingBasket } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * The live basket, as the agent left it.
 *
 * This renders server state rather than anything computed here. In particular the
 * "still needed" list comes from the server's readiness check, so the chat panel and the
 * cart page can no longer drift apart about what checkout requires - they previously
 * each had their own copy of those rules.
 *
 * For a signed-in customer this is their real cart, so what the agent changes here is
 * what they will find on the cart page. For a guest it is a draft held on the
 * conversation, which is what lets a WhatsApp-only customer order without an account.
 */

function formatMoney(currency = "PKR", value = 0) {
  return `${currency} ${Number(value || 0).toLocaleString("en-PK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function BusinessAiBasketPanel({ basket = {}, readiness = {}, compact = false, cartLink = "/customer/cart" }) {
  const lines = basket.lines || [];
  const isEmpty = basket.isEmpty ?? !lines.length;
  const currency = basket.currency || "PKR";
  const missing = readiness.missing || [];
  const isGuestDraft = basket.kind === "draft";

  if (!basket.kind) {
    return null;
  }

  return (
    <div className={compact ? "rounded-2xl border border-brand-100 bg-white p-3 shadow-card" : "rounded-[30px] border border-white/80 bg-white p-5 shadow-xl shadow-slate-200/70"}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShoppingBasket size={16} className="text-brand" />
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-brand-700">Your cart</div>
        </div>
        {!isEmpty ? (
          <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-bold text-brand">
            {basket.itemCount} item{basket.itemCount === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      {isEmpty ? (
        <p className="mt-3 text-sm leading-6 text-muted">
          Your cart is empty. Tell the assistant what you would like, for example
          {" "}<span className="font-semibold text-ink">&ldquo;add 2 burgers&rdquo;</span>.
        </p>
      ) : (
        <>
          <ul className="mt-3 divide-y divide-line-soft">
            {lines.map((line) => (
              <li key={line.lineId} className="flex items-start justify-between gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="break-words text-sm font-semibold leading-snug text-ink">
                    {line.quantity} &times; {line.name}
                  </div>
                  {line.selectedVariantName ? (
                    <div className="break-words text-[11px] font-semibold leading-snug text-brand">
                      {line.selectedVariantName}
                    </div>
                  ) : null}
                  <div className="mt-0.5 text-[11px] text-muted">
                    {formatMoney(line.currency || currency, line.unitPrice)} each
                  </div>
                </div>
                <div className="shrink-0 whitespace-nowrap text-sm font-bold text-ink">
                  {formatMoney(currency, line.subtotal)}
                </div>
              </li>
            ))}
          </ul>

          <div className="mt-3 flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 border-t border-line pt-3">
            <span className="text-xs font-bold uppercase tracking-wider text-subtle">Subtotal</span>
            <span className="whitespace-nowrap text-base font-extrabold text-ink">
              {formatMoney(currency, basket.subtotal)}
            </span>
          </div>
        </>
      )}

      {/* The readiness list is the server's, not this component's. */}
      {!isEmpty && missing.length ? (
        <div className="mt-3 rounded-xl border border-orange-200 bg-orange-50 px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-orange-700">
            <AlertCircle size={13} />
            Still needed
          </div>
          <ul className="mt-1.5 space-y-0.5 text-xs leading-5 text-orange-800">
            {missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {!isEmpty && readiness.canCheckout ? (
        <div className="mt-3 flex items-center gap-1.5 rounded-xl border border-green-200 bg-green-50 px-3 py-2.5 text-xs font-bold text-green-700">
          <CheckCircle2 size={14} />
          Ready to place your order.
        </div>
      ) : null}

      {!isEmpty && !isGuestDraft ? (
        <Link
          to={cartLink}
          className="mt-3 flex w-full items-center justify-center rounded-2xl bg-brand px-4 py-2.5 text-sm font-bold text-white transition hover:bg-brand-hover"
        >
          Open cart &amp; checkout
        </Link>
      ) : null}

      {isGuestDraft && !isEmpty ? (
        <p className="mt-3 text-[11px] leading-5 text-muted">
          Tell the assistant to place your order when you are ready, and it will ask for
          the details it still needs.
        </p>
      ) : null}
    </div>
  );
}
