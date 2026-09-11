import { getDefaultPaymentMethod, getSelectedPaymentMethod } from "./paymentMethods.js";

function methodSummary(method = {}) {
  const rows = [
    ["Account title", method.accountTitle],
    ["Account / Number", method.accountNumber],
    ["Bank", method.bankName],
    ["IBAN", method.iban],
  ].filter(([, value]) => value);
  return rows;
}

export function CustomerPaymentInstructions({ options = {}, selectedMethod = "", onChange, compact = false }) {
  const methods = options.methods || [];
  const selectedCode = selectedMethod || getDefaultPaymentMethod(options);
  const selected = getSelectedPaymentMethod(options, selectedCode);

  if (!methods.length) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-4 text-sm text-slate-500">
        Payment instructions are not configured yet. The business owner will confirm payment manually.
      </div>
    );
  }

  const rows = methodSummary(selected);

  return (
    <div className={compact ? "rounded-2xl border border-brand-100 bg-brand-50/60 p-3" : "rounded-3xl border border-brand-100 bg-brand-50/60 p-4"}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-brand-700">Payment</div>
          <h3 className={compact ? "mt-1 text-sm font-bold text-slate-950" : "mt-1 text-lg font-bold text-slate-950"}>Choose how you want to pay</h3>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {selected?.description || "Select a payment method. The owner verifies manual payments before marking them paid."}
          </p>
        </div>
        {options.paymentsDemoMode ? (
          <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-[11px] font-bold text-amber-800">Demo mode</span>
        ) : null}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {methods.map((method) => (
          <button
            key={method.code}
            type="button"
            className={
              selectedCode === method.code
                ? "rounded-2xl border border-brand-300 bg-white px-3 py-3 text-left text-sm font-bold text-brand-800 shadow-card"
                : "rounded-2xl border border-slate-200 bg-white/70 px-3 py-3 text-left text-sm font-semibold text-slate-700"
            }
            onClick={() => onChange?.(method.code)}
          >
            {method.label}
          </button>
        ))}
      </div>

      {selected ? (
        <div className="mt-3 rounded-2xl border border-white bg-white/80 p-3 text-sm">
          <div className="font-bold text-slate-950">{selected.label}</div>
          {rows.length ? (
            <div className="mt-2 grid gap-2 text-xs text-slate-600">
              {rows.map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
                  <span>{label}</span>
                  <span className="text-right font-semibold text-slate-950">{value}</span>
                </div>
              ))}
            </div>
          ) : null}
          {options.customerInstructions ? <p className="mt-3 text-xs leading-5 text-slate-600">{options.customerInstructions}</p> : null}
          {selected.requiresOwnerApproval ? (
            <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
              Send the payment reference to the business. Your payment will show as unpaid until the owner verifies it.
            </p>
          ) : selected.isOnline ? (
            <div className="mt-3 space-y-2">
              <p className="rounded-xl bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-800">
                You will be taken to the {selected.label} payment page and returned here once the payment is done.
              </p>
              {selected.code === "stripe_test" && selected.mode !== "live" ? (
                <p className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-700">
                  Test mode: use card {selected.testCard || "4242 4242 4242 4242"} with any future expiry and any CVC.
                </p>
              ) : null}
              {selected.simulated ? (
                <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
                  Simulated gateway: no real money moves. Replace it with live {selected.label} credentials before launch.
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 rounded-xl bg-green-50 px-3 py-2 text-xs font-semibold text-green-800">
              Cash will be collected by the business. No online payment is needed right now.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
