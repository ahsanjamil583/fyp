import { createCustomerStripeCheckout, startGatewayCheckout } from "./customerPortalApi.js";

// Methods that take the customer away to a payment page instead of being settled by the
// business later. Kept here so the cart and the order page agree on what "online" means.
export const ONLINE_PAYMENT_METHODS = new Set(["stripe_test", "jazzcash", "easypaisa"]);

export function isOnlinePaymentMethod(method) {
  return ONLINE_PAYMENT_METHODS.has(String(method || ""));
}

/**
 * Leave the app for a payment gateway.
 *
 * Gateways differ in how they want to be entered: Stripe and the local simulator take a
 * plain URL, while JazzCash expects a form POST carrying the signed fields. Submitting a
 * generated form covers the POST case without needing the fields in the address bar,
 * where they would leak into history and logs.
 */
export function redirectToGateway(redirect) {
  const { url, method = "GET", fields = {} } = redirect || {};
  if (!url) throw new Error("The payment gateway did not return a redirect target.");

  if (String(method).toUpperCase() !== "POST") {
    window.location.assign(url);
    return;
  }

  const form = document.createElement("form");
  form.method = "POST";
  form.action = url;
  form.style.display = "none";
  Object.entries(fields).forEach(([name, value]) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value == null ? "" : String(value);
    form.appendChild(input);
  });
  document.body.appendChild(form);
  form.submit();
}

/**
 * Send the customer to whichever gateway backs the chosen method.
 *
 * Returns false when the method is settled offline (cash, bank transfer), so the caller
 * can fall through to its normal "order placed" path.
 */
export async function startOnlinePayment(orderId, method) {
  if (!isOnlinePaymentMethod(method)) return false;

  if (method === "stripe_test") {
    const session = await createCustomerStripeCheckout(orderId, {});
    if (!session?.checkoutUrl) throw new Error("Stripe did not return a checkout URL.");
    window.location.assign(session.checkoutUrl);
    return true;
  }

  const checkout = await startGatewayCheckout(orderId, method);
  redirectToGateway(checkout?.redirect);
  return true;
}
