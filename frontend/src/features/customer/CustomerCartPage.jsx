import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, CreditCard, MapPin, Receipt, ShoppingCart } from "lucide-react";

import { DynamicForm } from "../../components/dynamic/DynamicForm.jsx";
import { CustomerPaymentInstructions } from "../../components/payments/CustomerPaymentInstructions.jsx";
import { getDefaultPaymentMethod } from "../../components/payments/paymentMethods.js";
import { isOnlinePaymentMethod, startOnlinePayment } from "../../services/paymentRedirect.js";
import { createCustomerTransaction, getCustomerCart, removeCartItem, updateCartItem } from "../../services/customerPortalApi.js";
import { formatApiError } from "../../utils/apiErrors.js";
import { capitalize, formatTransactionLabel, formatTransactionSuccess, transactionTypeOptions } from "../../utils/transaction.js";

export function CustomerCartPage() {
  const navigate = useNavigate();
  const [carts, setCarts] = useState([]);
  const [transactionTypes, setTransactionTypes] = useState({});
  const [checkoutDrafts, setCheckoutDrafts] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    refreshCart();
  }, []);

  async function refreshCart() {
    const data = await getCustomerCart();
    setCarts(data);
    setTransactionTypes((current) => {
      const next = { ...current };
      data.forEach((cart) => {
        if (!(cart.tenantId in next)) {
          next[cart.tenantId] = "auto";
        }
      });
      return next;
    });
    setCheckoutDrafts((current) => {
      const next = { ...current };
      data.forEach((cart) => {
        if (!(cart.tenantId in next)) {
          const defaultValues = Object.fromEntries(
            (cart.checkoutConfig?.transactionCustomFields || []).map((field) => [field.key, field.defaultValue ?? ""]),
          );
          next[cart.tenantId] = {
            fulfillmentType: cart.checkoutConfig?.defaultFulfillmentType || "none",
            paymentMethod: getDefaultPaymentMethod(cart.checkoutConfig?.paymentOptions || {}),
            addressLine1: "",
            addressCity: "",
            notes: "",
            customFields: defaultValues,
          };
        }
      });
      return next;
    });
  }

  async function changeQuantity(itemId, quantity) {
    await updateCartItem(itemId, { quantity: Number(quantity) });
    await refreshCart();
  }

  async function removeItem(itemId) {
    await removeCartItem(itemId);
    await refreshCart();
  }

  async function checkout(tenantId) {
    setMessage("");
    setError("");
    const draft = checkoutDrafts[tenantId] || {};
    try {
      const transaction = await createCustomerTransaction({
        tenantId,
        transactionType: transactionTypes[tenantId] || "auto",
        paymentMethod: draft.paymentMethod || undefined,
        fulfillment: {
          type: draft.fulfillmentType || "none",
          address:
            draft.fulfillmentType === "delivery"
              ? { line1: draft.addressLine1 || "", city: draft.addressCity || "" }
              : {},
        },
        notes: draft.notes || "",
        customFields: draft.customFields || {},
      });
      await refreshCart();

      // An online method continues straight to the gateway, so placing the order and
      // paying feel like one step. The order already exists at this point, which is what
      // the payment is recorded against and what the customer returns to.
      if (isOnlinePaymentMethod(draft.paymentMethod)) {
        setMessage("Order placed. Taking you to the payment page...");
        try {
          await startOnlinePayment(transaction.id, draft.paymentMethod);
          return;
        } catch (paymentError) {
          // The order exists either way, so this must not read like the checkout failed.
          // Send them to it, where the payment can be retried.
          setMessage("");
          setError(
            formatApiError(
              paymentError.response?.data?.detail,
              "Your order was placed, but the payment page could not be opened. Open the order to try paying again.",
            ),
          );
          navigate(`/customer/orders/${transaction.id}`);
          return;
        }
      }

      setMessage(formatTransactionSuccess(transaction));
      navigate(`/customer/orders/${transaction.id}`);
    } catch (requestError) {
      setError(formatApiError(requestError.response?.data?.detail, "Unable to checkout cart."));
    }
  }

  function updateCheckoutDraft(tenantId, key, value) {
    setCheckoutDrafts((current) => ({
      ...current,
      [tenantId]: {
        fulfillmentType: current[tenantId]?.fulfillmentType || "none",
        paymentMethod: current[tenantId]?.paymentMethod || "",
        addressLine1: current[tenantId]?.addressLine1 || "",
        addressCity: current[tenantId]?.addressCity || "",
        notes: current[tenantId]?.notes || "",
        customFields: current[tenantId]?.customFields || {},
        [key]: value,
      },
    }));
  }

  function updateCheckoutCustomFields(tenantId, values) {
    setCheckoutDrafts((current) => ({
      ...current,
      [tenantId]: {
        fulfillmentType: current[tenantId]?.fulfillmentType || "none",
        paymentMethod: current[tenantId]?.paymentMethod || "",
        addressLine1: current[tenantId]?.addressLine1 || "",
        addressCity: current[tenantId]?.addressCity || "",
        notes: current[tenantId]?.notes || "",
        customFields: values,
      },
    }));
  }

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Cart</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Cart & checkout</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Review items, choose delivery or pickup, select payment, then place the order. Each business checks out separately.
        </p>
        <div className="mt-5 grid gap-2 text-xs font-bold text-muted sm:grid-cols-4">
          {[
            ["1", "Review cart"],
            ["2", "Delivery details"],
            ["3", "Payment"],
            ["4", "Track order"],
          ].map(([n, label]) => (
            <div key={label} className="rounded-xl border border-line bg-white px-3 py-3">
              <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-brand text-xs text-white">{n}</span>
              {label}
            </div>
          ))}
        </div>
      </div>
      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      <div className="space-y-5">
        {carts.map((cart) => {
          const total = cart.itemsDetailed.reduce((sum, item) => sum + (Number(item.price || 0) * Number(item.quantity || 0)), 0);
          const checkoutConfig = cart.checkoutConfig || {};
          const allowedFulfillmentTypes = checkoutConfig.allowedFulfillmentTypes || ["none"];
          const checkoutDraft = checkoutDrafts[cart.tenantId] || {
            fulfillmentType: checkoutConfig.defaultFulfillmentType || "none",
            paymentMethod: getDefaultPaymentMethod(checkoutConfig.paymentOptions || {}),
            addressLine1: "",
            addressCity: "",
            notes: "",
            customFields: {},
          };
          return (
            <div key={cart.id} className="rounded-xl border border-line bg-white p-5 shadow-card">
              <div className="flex flex-col gap-3 border-b border-line pb-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-base font-bold text-ink">
                    <ShoppingCart size={18} className="text-brand" />
                    {cart.tenant?.name || "Business"}
                  </div>
                  <div className="mt-1 text-sm text-muted">{cart.itemsDetailed.length} items in this order</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <select
                    className="form-input min-w-44"
                    value={transactionTypes[cart.tenantId] || "auto"}
                    onChange={(event) => setTransactionTypes((current) => ({ ...current, [cart.tenantId]: event.target.value }))}
                  >
                    {transactionTypeOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {cart.tenant?.slug ? (
                    <Link className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink" to={`/customer/businesses/${cart.tenant.slug}`}>
                      Continue shopping
                    </Link>
                  ) : null}
                  <button type="button" className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" onClick={() => checkout(cart.tenantId)}>
                    {(transactionTypes[cart.tenantId] || "auto") === "auto" ? "Checkout" : capitalize(formatTransactionLabel(transactionTypes[cart.tenantId]))}
                  </button>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {cart.itemsDetailed.map((item) => (
                  <div key={`${cart.id}-${item.id}`} className="grid gap-3 rounded-xl border border-line p-4 md:grid-cols-[1fr_110px_120px_90px] md:items-center">
                    <div>
                      <div className="font-semibold text-ink">{item.name}</div>
                      <div className="text-sm text-muted">{item.currency} {item.price}</div>
                    </div>
                    <input className="form-input" min="1" type="number" value={item.quantity} onChange={(event) => changeQuantity(item.id, event.target.value)} />
                    <div className="text-sm font-semibold text-ink">{Number(item.price || 0) * Number(item.quantity || 0)}</div>
                    <button type="button" className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink" onClick={() => removeItem(item.id)}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-5 grid gap-4 rounded-xl border border-line bg-surface p-4 lg:grid-cols-2">
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-sm font-bold text-ink">
                    <MapPin size={16} className="text-brand" />
                    Delivery or pickup
                  </div>
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Fulfillment</span>
                    <select
                      className="form-input"
                      value={checkoutDraft.fulfillmentType || "none"}
                      onChange={(event) => updateCheckoutDraft(cart.tenantId, "fulfillmentType", event.target.value)}
                    >
                      {allowedFulfillmentTypes.map((value) => (
                        <option key={value} value={value}>
                          {capitalize(value.replaceAll("_", " "))}
                        </option>
                      ))}
                    </select>
                  </label>
                  {checkoutDraft.fulfillmentType === "delivery" ? (
                    <div className="grid gap-3">
                      <label className="block">
                        <span className="mb-1.5 block text-sm font-medium text-ink">Delivery address</span>
                        <input
                          className="form-input"
                          placeholder="Street, block, area"
                          value={checkoutDraft.addressLine1 || ""}
                          onChange={(event) => updateCheckoutDraft(cart.tenantId, "addressLine1", event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-sm font-medium text-ink">City</span>
                        <input
                          className="form-input"
                          placeholder="Lahore"
                          value={checkoutDraft.addressCity || ""}
                          onChange={(event) => updateCheckoutDraft(cart.tenantId, "addressCity", event.target.value)}
                        />
                      </label>
                    </div>
                  ) : null}
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Order notes</span>
                    <textarea
                      className="form-input min-h-24"
                      placeholder="Extra ketchup, no onions, call before delivery"
                      value={checkoutDraft.notes || ""}
                      onChange={(event) => updateCheckoutDraft(cart.tenantId, "notes", event.target.value)}
                    />
                  </label>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-bold text-ink">
                    <CreditCard size={16} className="text-brand" />
                    Payment and checkout details
                  </div>
                  <CustomerPaymentInstructions
                    options={checkoutConfig.paymentOptions || {}}
                    selectedMethod={checkoutDraft.paymentMethod || ""}
                    onChange={(value) => updateCheckoutDraft(cart.tenantId, "paymentMethod", value)}
                  />
                  {(checkoutConfig.transactionCustomFields || []).length ? (
                    <DynamicForm
                      fields={checkoutConfig.transactionCustomFields}
                      values={checkoutDraft.customFields || {}}
                      onChange={(values) => updateCheckoutCustomFields(cart.tenantId, values)}
                    />
                  ) : (
                    <div className="rounded-xl border border-dashed border-line bg-white p-4 text-sm text-muted">
                      No extra checkout fields are required for this business.
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-4 flex flex-col gap-3 rounded-xl bg-brand-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-xs font-bold uppercase tracking-[0.14em] text-brand">Estimated total</div>
                  <div className="mt-1 text-2xl font-black text-ink">{total}</div>
                </div>
                <button type="button" className="ui-btn-primary" onClick={() => checkout(cart.tenantId)}>
                  Place order
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>
          );
        })}
        {!carts.length ? (
          <div className="rounded-xl border border-dashed border-line bg-surface p-8 text-center">
            <Receipt className="mx-auto text-brand" size={30} />
            <div className="mt-3 font-bold text-ink">Your cart is empty</div>
            <p className="mt-1 text-sm text-muted">Browse the marketplace and add products or services when you are ready.</p>
            <Link className="ui-btn-primary mt-5" to="/customer/marketplace">
              Browse businesses
            </Link>
          </div>
        ) : null}
      </div>
    </section>
  );
}
