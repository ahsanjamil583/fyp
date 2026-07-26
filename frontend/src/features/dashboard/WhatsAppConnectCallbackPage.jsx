import { useEffect, useMemo } from "react";
import { Link, useLocation } from "react-router-dom";

export function WhatsAppConnectCallbackPage() {
  const location = useLocation();
  const callbackPayload = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const entries = {};
    params.forEach((value, key) => {
      entries[key] = value;
    });
    return {
      source: "redirect_callback",
      query: entries,
      hasAuthorizationCode: Boolean(entries.code),
      receivedAt: new Date().toISOString(),
    };
  }, [location.search]);

  useEffect(() => {
    sessionStorage.setItem("bizxus_meta_signup_redirect_callback", JSON.stringify(callbackPayload));
  }, [callbackPayload]);

  return (
    <section className="mx-auto max-w-2xl space-y-5 rounded-2xl border border-line bg-white p-6 shadow-sm">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">WhatsApp Embedded Signup</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Meta callback received</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          BizXusAI captured the browser callback from Meta. Return to the WhatsApp Agent page to continue the connection flow.
          Phase C will send this signup response to the backend for token exchange.
        </p>
      </div>
      <div className={callbackPayload.hasAuthorizationCode ? "rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700" : "rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"}>
        {callbackPayload.hasAuthorizationCode ? "Authorization code detected." : "No authorization code was found in the callback URL."}
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-4 text-xs text-slate-100">
        {JSON.stringify(callbackPayload, null, 2)}
      </pre>
      <Link className="inline-flex rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white" to="/dashboard/whatsapp-agent">
        Back to WhatsApp Agent
      </Link>
    </section>
  );
}
