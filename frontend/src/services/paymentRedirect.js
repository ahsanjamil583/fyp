import { createCustomerStripeCheckout, startGatewayCheckout } from "./customerPortalApi.js";

// Methods that are settled by a provider rather than by the business later. Kept here so
// the cart and the order page agree on what "online" means.
export const ONLINE_PAYMENT_METHODS = new Set(["stripe_test", "jazzcash", "easypaisa"]);

export function isOnlinePaymentMethod(method) {
  return ONLINE_PAYMENT_METHODS.has(String(method || ""));
}

/**
 * Which shape of payment a method uses.
 *
 * The server decides this, not the client: each provider reports its own `flow` in the
 * payment options attached to the order. A wallet configured for emailed codes reports
 * `otp`, the same wallet pointed at the real gateway reports `redirect`, and this file
 * is the only place that has to care.
 */
export function paymentFlowFor(methodDetails) {
  return String(methodDetails?.flow || "redirect");
}

export function isOtpPaymentMethod(methodDetails) {
  return paymentFlowFor(methodDetails) === "otp";
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
 * Take the customer to whichever provider backs the chosen method.
 *
 * Returns one of:
 *   `{ handled: false }`          the method settles offline (cash, bank transfer)
 *   `{ handled: true }`           the browser is leaving for a gateway
 *   `{ handled: true, otp: true } the caller should open the code dialog instead
 *
 * The OTP case deliberately does not navigate: the customer stays on the order page and
 * finishes there, which is the whole point of that flow.
 */
export async function startOnlinePayment(orderId, method, methodDetails = null) {
  if (!isOnlinePaymentMethod(method)) return { handled: false };

  if (isOtpPaymentMethod(methodDetails)) {
    return { handled: true, otp: true, method, methodDetails };
  }

  if (method === "stripe_test") {
    const session = await createCustomerStripeCheckout(orderId, {});
    if (!session?.checkoutUrl) throw new Error("Stripe did not return a checkout URL.");
    window.location.assign(session.checkoutUrl);
    return { handled: true };
  }

  const checkout = await startGatewayCheckout(orderId, method);
  redirectToGateway(checkout?.redirect);
  return { handled: true };
}
