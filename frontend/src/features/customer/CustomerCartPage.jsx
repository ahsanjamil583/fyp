import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { DynamicForm } from "../../components/dynamic/DynamicForm.jsx";
import { CustomerPaymentInstructions, getDefaultPaymentMethod } from "../../components/payments/CustomerPaymentInstructions.jsx";
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
      setMessage(formatTransactionSuccess(transaction));
      await refreshCart();
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
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Cart</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Customer Cart</h1>
      </div>
      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
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
            <div key={cart.id} className="rounded-md border border-line bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 border-b border-line pb-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="text-lg font-semibold text-ink">{cart.tenant?.name || "Business"}</div>
                  <div className="mt-1 text-sm text-muted">{cart.itemsDetailed.length} items</div>
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
                    <Link className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" to={`/customer/businesses/${cart.tenant.slug}`}>
                      Continue shopping
                    </Link>
                  ) : null}
                  <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" onClick={() => checkout(cart.tenantId)}>
                    {(transactionTypes[cart.tenantId] || "auto") === "auto" ? "Checkout" : capitalize(formatTransactionLabel(transactionTypes[cart.tenantId]))}
                  </button>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {cart.itemsDetailed.map((item) => (
                  <div key={`${cart.id}-${item.id}`} className="grid gap-3 rounded-md border border-line p-4 md:grid-cols-[1fr_110px_120px_90px] md:items-center">
                    <div>
                      <div className="font-semibold text-ink">{item.name}</div>
                      <div className="text-sm text-muted">{item.currency} {item.price}</div>
                    </div>
                    <input className="form-input" min="1" type="number" value={item.quantity} onChange={(event) => changeQuantity(item.id, event.target.value)} />
                    <div className="text-sm font-semibold text-ink">{Number(item.price || 0) * Number(item.quantity || 0)}</div>
                    <button className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink" onClick={() => removeItem(item.id)}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-5 grid gap-4 rounded-md border border-line bg-surface p-4 lg:grid-cols-2">
                <div className="space-y-4">
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
                  <div className="text-sm font-semibold text-ink">Checkout details</div>
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
                    <div className="rounded-md border border-dashed border-line bg-white p-4 text-sm text-muted">
                      No extra checkout fields are required for this business.
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-4 text-right text-sm font-semibold text-ink">Estimated total: {total}</div>
            </div>
          );
        })}
        {!carts.length ? (
          <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted">Your cart is empty.</div>
        ) : null}
      </div>
    </section>
  );
}
