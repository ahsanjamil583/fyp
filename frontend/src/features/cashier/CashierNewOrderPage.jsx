import { AlertTriangle, Minus, PackagePlus, Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Card } from "../../components/ui/index.jsx";
import { createCashierOrder, getCashierCatalog, getCashierDashboard } from "../../services/cashierApi.js";
import { formatMoney } from "./cashierShared.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

/**
 * The till screen.
 *
 * Two columns on a desktop counter, stacked on a phone: search and tap items on the
 * left, the running bill on the right. The totals are computed here for instant
 * feedback, but the server recomputes them from the same rules before saving - the
 * figure printed on the receipt is always the server's, never this one's.
 */

const EMPTY_CUSTOMER = { customerName: "", customerPhone: "", customerEmail: "" };

function lineKey(item, variantIndex) {
  return `${item.id}:${variantIndex ?? "base"}`;
}

export function CashierNewOrderPage() {
  const navigate = useNavigate();
  const [options, setOptions] = useState({ paymentMethods: [], serviceTypes: [], currency: "PKR", permissions: {} });
  const [search, setSearch] = useState("");
  const [catalog, setCatalog] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [lines, setLines] = useState([]);
  const [customer, setCustomer] = useState(EMPTY_CUSTOMER);
  const [charges, setCharges] = useState({
    discountType: "amount",
    discountValue: "",
    taxType: "amount",
    taxValue: "",
    serviceCharge: "",
    deliveryFee: "",
  });
  const [serviceType, setServiceType] = useState("in_store");
  const [address, setAddress] = useState({ line1: "", city: "" });
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [amountReceived, setAmountReceived] = useState("");
  const [notes, setNotes] = useState("");
  const [customDraft, setCustomDraft] = useState({ name: "", unitPrice: "", quantity: 1 });
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getCashierDashboard()
      .then((data) =>
        setOptions({
          paymentMethods: data.paymentMethods || [],
          serviceTypes: data.serviceTypes || [],
          currency: data.business?.currency || "PKR",
          permissions: data.cashier?.permissions || {},
        }),
      )
      .catch(() => {});
  }, []);

  const loadCatalog = useCallback(async (term) => {
    setIsSearching(true);
    try {
      setCatalog(await getCashierCatalog({ search: term || undefined, limit: 40 }));
    } catch {
      setCatalog([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    const timerId = window.setTimeout(() => loadCatalog(search), search ? 250 : 0);
    return () => window.clearTimeout(timerId);
  }, [search, loadCatalog]);

  const currency = options.currency;
  const permissions = options.permissions;

  function addCatalogLine(item, variant = null) {
    const key = lineKey(item, variant?.index);
    setLines((current) => {
      const existing = current.find((line) => line.key === key);
      if (existing) {
        // 99 is what the backend enforces per line; 999 here meant the till let a
        // cashier build an order the API would then refuse.
        return current.map((line) => (line.key === key ? { ...line, quantity: Math.min(line.quantity + 1, 99) } : line));
      }
      return [
        ...current,
        {
          key,
          itemId: item.id,
          name: variant ? `${item.name} — ${variant.name}` : item.name,
          unitPrice: Number(variant?.price ?? item.price ?? 0),
          quantity: 1,
          selectedVariantIndex: variant ? variant.index : null,
          isStockTracked: item.isStockTracked,
          availableQuantity: variant ? variant.availableQuantity : item.availableQuantity,
          isCustom: false,
        },
      ];
    });
  }

  function addCustomLine() {
    const name = customDraft.name.trim();
    const unitPrice = Number(customDraft.unitPrice);
    if (name.length < 2 || !Number.isFinite(unitPrice) || unitPrice < 0) {
      setError("A manual item needs a name and a price.");
      return;
    }
    setError("");
    setLines((current) => [
      ...current,
      {
        key: `custom:${Date.now()}`,
        itemId: "",
        name,
        unitPrice,
        // Capped at the same 99 the API enforces. Narrowing the schema without clamping
        // here meant a manual line above 99 was accepted by the till and refused by the
        // server.
        quantity: Math.max(1, Math.min(99, Math.floor(Number(customDraft.quantity) || 1))),
        selectedVariantIndex: null,
        isStockTracked: false,
        availableQuantity: null,
        isCustom: true,
      },
    ]);
    setCustomDraft({ name: "", unitPrice: "", quantity: 1 });
  }

  function changeQuantity(key, delta) {
    setLines((current) =>
      current
        // Capped at the same 99 the API enforces, like the two sibling handlers above.
        .map((line) => (line.key === key ? { ...line, quantity: Math.min(99, Math.max(0, line.quantity + delta)) } : line))
        .filter((line) => line.quantity > 0),
    );
  }

  function removeLine(key) {
    setLines((current) => current.filter((line) => line.key !== key));
  }

  const totals = useMemo(() => {
    const subtotal = lines.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0);
    const discountValue = Number(charges.discountValue) || 0;
    const discount = charges.discountType === "percent" ? (subtotal * Math.min(discountValue, 100)) / 100 : Math.min(discountValue, subtotal);
    const base = Math.max(0, subtotal - discount);
    const taxValue = Number(charges.taxValue) || 0;
    const tax = charges.taxType === "percent" ? (base * Math.min(taxValue, 100)) / 100 : taxValue;
    const serviceCharge = Number(charges.serviceCharge) || 0;
    const deliveryFee = Number(charges.deliveryFee) || 0;
    const total = base + tax + serviceCharge + deliveryFee;
    return { subtotal, discount, tax, serviceCharge, deliveryFee, total };
  }, [lines, charges]);

  const stockWarnings = lines.filter(
    (line) => line.isStockTracked && line.availableQuantity !== null && line.quantity > Number(line.availableQuantity || 0),
  );
  const changeDue = paymentMethod !== "unpaid" && amountReceived !== "" ? Number(amountReceived) - totals.total : null;

  async function submit(event) {
    event.preventDefault();
    if (!lines.length) {
      setError("Add at least one item before saving the order.");
      return;
    }
    if (stockWarnings.length) {
      setError(`Not enough stock for ${stockWarnings.map((line) => line.name).join(", ")}. Reduce the quantity or use a manual item.`);
      return;
    }
    setError("");
    setIsSaving(true);
    try {
      const result = await createCashierOrder({
        ...customer,
        items: lines.map((line) => ({
          itemId: line.itemId || "",
          name: line.isCustom ? line.name : "",
          quantity: line.quantity,
          unitPrice: line.isCustom ? line.unitPrice : null,
          selectedVariantIndex: line.selectedVariantIndex,
        })),
        discountType: charges.discountType,
        discountValue: Number(charges.discountValue) || 0,
        taxType: charges.taxType,
        taxValue: Number(charges.taxValue) || 0,
        serviceCharge: Number(charges.serviceCharge) || 0,
        deliveryFee: Number(charges.deliveryFee) || 0,
        serviceType,
        address: serviceType === "delivery" ? address : {},
        paymentMethod,
        amountReceived: amountReceived === "" ? null : Number(amountReceived),
        notes,
      });
      navigate(`/cashier/receipts/${result.order.receiptToken}?created=1`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to save this order."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="space-y-5" onSubmit={submit}>
      <header>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Counter</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">New order</h1>
      </header>

      {error ? <Alert tone="red">{error}</Alert> : null}
      {stockWarnings.length ? (
        <div className="flex items-start gap-2 rounded-xl border border-orange-200 bg-orange-50 px-4 py-3 text-sm font-semibold text-orange-700">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <span>
            Not enough stock for {stockWarnings.map((line) => `${line.name} (${line.availableQuantity} left)`).join(", ")}. Confirming will be blocked
            until the quantity fits.
          </span>
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        {/* ---------------------------------------------------------- catalog -- */}
        <div className="space-y-4">
          <Card>
            <label className="relative block">
              <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input
                className="form-input pl-11 text-base"
                placeholder="Search the catalog by name or SKU"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>

            <div className="mt-4 max-h-[22rem] space-y-2 overflow-y-auto pr-1">
              {isSearching ? <div className="py-4 text-center text-sm text-muted">Searching...</div> : null}
              {!isSearching && !catalog.length ? (
                <div className="rounded-xl border border-dashed border-line bg-surface px-4 py-6 text-center text-sm text-muted">
                  No catalog items matched. Add the item by hand below.
                </div>
              ) : null}
              {catalog.map((item) => (
                <div key={item.id} className="rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-bold text-ink">{item.name}</div>
                      <div className="truncate text-xs text-muted">
                        {formatMoney(item.price, currency)}
                        {item.sku ? ` · ${item.sku}` : ""}
                        {item.isStockTracked ? ` · ${item.availableQuantity} in stock` : " · stock not tracked"}
                      </div>
                    </div>
                    {item.variants.length ? null : (
                      <button type="button" className="ui-btn-primary px-4 py-2.5" onClick={() => addCatalogLine(item)}>
                        <Plus size={16} />
                        Add
                      </button>
                    )}
                  </div>
                  {item.variants.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {item.variants.map((variant) => (
                        <button
                          key={variant.index}
                          type="button"
                          className="rounded-lg border border-line bg-white px-3 py-2 text-xs font-bold text-ink transition hover:bg-brand-50"
                          onClick={() => addCatalogLine(item, variant)}
                        >
                          {variant.name || `Option ${variant.index + 1}`} · {formatMoney(variant.price, currency)}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>

          {permissions.canAddCustomItems !== false ? (
            <Card>
              <h2 className="mb-3 flex items-center gap-2 text-base font-bold text-ink">
                <PackagePlus size={18} className="text-brand" />
                Item not in the catalog
              </h2>
              <div className="grid gap-3 sm:grid-cols-[1.6fr_0.8fr_0.6fr_auto]">
                <input
                  className="form-input"
                  placeholder="Item name"
                  value={customDraft.name}
                  onChange={(event) => setCustomDraft((current) => ({ ...current, name: event.target.value }))}
                />
                <input
                  className="form-input"
                  placeholder="Unit price"
                  inputMode="decimal"
                  value={customDraft.unitPrice}
                  onChange={(event) => setCustomDraft((current) => ({ ...current, unitPrice: event.target.value }))}
                />
                <input
                  className="form-input"
                  placeholder="Qty"
                  inputMode="numeric"
                  value={customDraft.quantity}
                  onChange={(event) => setCustomDraft((current) => ({ ...current, quantity: event.target.value }))}
                />
                <button type="button" className="ui-btn-secondary" onClick={addCustomLine}>
                  Add line
                </button>
              </div>
              <p className="mt-2 text-xs text-muted">Manual items are not linked to the catalog, so they never change your stock counts.</p>
            </Card>
          ) : null}
        </div>

        {/* ------------------------------------------------------------- bill -- */}
        <div className="space-y-4">
          <Card>
            <h2 className="mb-3 text-base font-bold text-ink">Order lines</h2>
            {lines.length ? (
              <ul className="space-y-2">
                {lines.map((line) => (
                  <li key={line.key} className="flex flex-wrap items-center gap-2 rounded-xl border border-line px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-bold text-ink">{line.name}</div>
                      <div className="text-xs text-muted">
                        {formatMoney(line.unitPrice, currency)} each{line.isCustom ? " · manual item" : ""}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        aria-label={`Reduce ${line.name}`}
                        className="grid h-10 w-10 place-items-center rounded-lg border border-line bg-white text-ink transition hover:bg-surface"
                        onClick={() => changeQuantity(line.key, -1)}
                      >
                        <Minus size={16} />
                      </button>
                      <span className="w-9 text-center text-sm font-extrabold text-ink">{line.quantity}</span>
                      <button
                        type="button"
                        aria-label={`Add one ${line.name}`}
                        className="grid h-10 w-10 place-items-center rounded-lg border border-line bg-white text-ink transition hover:bg-surface"
                        onClick={() => changeQuantity(line.key, 1)}
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                    <div className="w-24 text-right text-sm font-extrabold text-ink">{formatMoney(line.unitPrice * line.quantity, currency)}</div>
                    <button
                      type="button"
                      aria-label={`Remove ${line.name}`}
                      className="grid h-10 w-10 place-items-center rounded-lg text-muted transition hover:bg-red-50 hover:text-red-500"
                      onClick={() => removeLine(line.key)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-xl border border-dashed border-line bg-surface px-4 py-8 text-center text-sm text-muted">
                Tap an item on the left to start the bill.
              </div>
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-base font-bold text-ink">Customer</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name">
                <input
                  className="form-input"
                  placeholder="Walk-in customer"
                  value={customer.customerName}
                  onChange={(event) => setCustomer((current) => ({ ...current, customerName: event.target.value }))}
                />
              </Field>
              <Field label="Phone">
                <input
                  className="form-input"
                  placeholder="03001234567"
                  inputMode="tel"
                  value={customer.customerPhone}
                  onChange={(event) => setCustomer((current) => ({ ...current, customerPhone: event.target.value }))}
                />
              </Field>
              <Field label="Email (optional)" className="sm:col-span-2">
                <input
                  className="form-input"
                  placeholder="customer@example.com"
                  value={customer.customerEmail}
                  onChange={(event) => setCustomer((current) => ({ ...current, customerEmail: event.target.value }))}
                />
              </Field>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-base font-bold text-ink">Charges</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {permissions.canApplyDiscount !== false ? (
                <Field label="Discount">
                  <div className="flex gap-2">
                    <input
                      className="form-input"
                      inputMode="decimal"
                      placeholder="0"
                      value={charges.discountValue}
                      onChange={(event) => setCharges((current) => ({ ...current, discountValue: event.target.value }))}
                    />
                    <select
                      className="form-input w-28"
                      value={charges.discountType}
                      onChange={(event) => setCharges((current) => ({ ...current, discountType: event.target.value }))}
                    >
                      <option value="amount">{currency}</option>
                      <option value="percent">%</option>
                    </select>
                  </div>
                </Field>
              ) : null}
              <Field label="Tax / GST">
                <div className="flex gap-2">
                  <input
                    className="form-input"
                    inputMode="decimal"
                    placeholder="0"
                    value={charges.taxValue}
                    onChange={(event) => setCharges((current) => ({ ...current, taxValue: event.target.value }))}
                  />
                  <select
                    className="form-input w-28"
                    value={charges.taxType}
                    onChange={(event) => setCharges((current) => ({ ...current, taxType: event.target.value }))}
                  >
                    <option value="amount">{currency}</option>
                    <option value="percent">%</option>
                  </select>
                </div>
              </Field>
              <Field label="Service charge">
                <input
                  className="form-input"
                  inputMode="decimal"
                  placeholder="0"
                  value={charges.serviceCharge}
                  onChange={(event) => setCharges((current) => ({ ...current, serviceCharge: event.target.value }))}
                />
              </Field>
              <Field label="Delivery fee">
                <input
                  className="form-input"
                  inputMode="decimal"
                  placeholder="0"
                  value={charges.deliveryFee}
                  onChange={(event) => setCharges((current) => ({ ...current, deliveryFee: event.target.value }))}
                />
              </Field>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-base font-bold text-ink">Order type and payment</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Order type">
                <select className="form-input" value={serviceType} onChange={(event) => setServiceType(event.target.value)}>
                  {options.serviceTypes.map((type) => (
                    <option key={type.code} value={type.code}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Payment method">
                <select className="form-input" value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}>
                  {options.paymentMethods.map((method) => (
                    <option key={method.code} value={method.code}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </Field>
              {serviceType === "delivery" ? (
                <>
                  <Field label="Address line">
                    <input className="form-input" value={address.line1} onChange={(event) => setAddress((current) => ({ ...current, line1: event.target.value }))} />
                  </Field>
                  <Field label="City">
                    <input className="form-input" value={address.city} onChange={(event) => setAddress((current) => ({ ...current, city: event.target.value }))} />
                  </Field>
                </>
              ) : null}
              {paymentMethod !== "unpaid" ? (
                <Field label="Amount received (optional)">
                  <input className="form-input" inputMode="decimal" value={amountReceived} onChange={(event) => setAmountReceived(event.target.value)} />
                </Field>
              ) : null}
              <Field label="Notes" className="sm:col-span-2">
                <textarea className="form-input min-h-20" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Anything to remember about this sale" />
              </Field>
            </div>
          </Card>

          <Card className="sticky bottom-4 border-brand-200 bg-brand-50">
            <dl className="space-y-1.5 text-sm">
              <Row label="Subtotal" value={formatMoney(totals.subtotal, currency)} />
              {totals.discount ? <Row label="Discount" value={`- ${formatMoney(totals.discount, currency)}`} /> : null}
              {totals.tax ? <Row label="Tax" value={formatMoney(totals.tax, currency)} /> : null}
              {totals.serviceCharge ? <Row label="Service charge" value={formatMoney(totals.serviceCharge, currency)} /> : null}
              {totals.deliveryFee ? <Row label="Delivery" value={formatMoney(totals.deliveryFee, currency)} /> : null}
              <div className="flex items-center justify-between border-t border-brand-200 pt-2 text-lg font-extrabold text-ink">
                <span>Total</span>
                <span>{formatMoney(totals.total, currency)}</span>
              </div>
              {changeDue !== null && changeDue >= 0 ? <Row label="Change due" value={formatMoney(changeDue, currency)} /> : null}
            </dl>
            <button type="submit" className="ui-btn-primary mt-4 w-full py-4 text-base" disabled={isSaving || !lines.length}>
              {isSaving ? "Saving..." : `Confirm and print · ${formatMoney(totals.total, currency)}`}
            </button>
          </Card>
        </div>
      </div>
    </form>
  );
}

function Field({ label, className = "", children }) {
  return (
    <label className={`block space-y-1.5 text-sm font-semibold text-ink ${className}`.trim()}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between text-muted">
      <dt>{label}</dt>
      <dd className="font-bold text-ink">{value}</dd>
    </div>
  );
}
