import { Mail, MessageCircle, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Alert, Card } from "../../components/ui/index.jsx";
import { getOrderMessageSettings, updateOrderMessageSettings } from "../../services/notificationApi.js";
import { getApiErrorMessage } from "../../services/apiError.js";

/**
 * Owner controls for the confirmations customers receive.
 *
 * Defaults are on, so a business that never opens this panel still confirms its orders —
 * which is what a customer expects. The panel exists so a business that would rather stay
 * quiet, or has no mail server, can say so.
 */

const DEFAULTS = {
  emailEnabled: true,
  whatsappEnabled: true,
  sendOnOrderPlaced: true,
  sendOnPaymentConfirmed: true,
  footerNote: "",
};

export function OrderMessageSettings({ tenantId }) {
  const [form, setForm] = useState(DEFAULTS);
  const [emailConfigured, setEmailConfigured] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const load = useCallback(async () => {
    if (!tenantId) return;
    try {
      const data = await getOrderMessageSettings(tenantId);
      setForm({
        emailEnabled: data.emailEnabled,
        whatsappEnabled: data.whatsappEnabled,
        sendOnOrderPlaced: data.sendOnOrderPlaced,
        sendOnPaymentConfirmed: data.sendOnPaymentConfirmed,
        footerNote: data.footerNote || "",
      });
      setEmailConfigured(Boolean(data.emailConfigured));
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load order message settings."));
    }
  }, [tenantId]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(event) {
    event.preventDefault();
    setIsSaving(true);
    setMessage("");
    setError("");
    try {
      await updateOrderMessageSettings(tenantId, form);
      setMessage("Order message settings saved.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to save order message settings."));
    } finally {
      setIsSaving(false);
    }
  }

  function toggle(key) {
    setForm((current) => ({ ...current, [key]: !current[key] }));
  }

  if (!tenantId) return null;

  return (
    <Card as="form" onSubmit={save} className="space-y-4">
      <div>
        <h2 className="text-base font-bold text-ink">Order confirmations</h2>
        <p className="mt-1 text-sm leading-6 text-muted">
          What customers receive after ordering. Every message links to a printable receipt.
          Counter sales and imported orders are never messaged.
        </p>
      </div>

      {message ? <Alert tone="green">{message}</Alert> : null}
      {error ? <Alert tone="red">{error}</Alert> : null}

      {!emailConfigured ? (
        <Alert tone="orange">
          SMTP is not configured on this server, so email confirmations will be skipped until it is.
        </Alert>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-2">
        <Toggle
          checked={form.emailEnabled}
          icon={Mail}
          label="Email the customer"
          hint="Uses the address on the order."
          onChange={() => toggle("emailEnabled")}
        />
        <Toggle
          checked={form.whatsappEnabled}
          icon={MessageCircle}
          label="Message on WhatsApp"
          hint="Only when your WhatsApp number is connected."
          onChange={() => toggle("whatsappEnabled")}
        />
        <Toggle
          checked={form.sendOnOrderPlaced}
          label="When an order is placed"
          onChange={() => toggle("sendOnOrderPlaced")}
        />
        <Toggle
          checked={form.sendOnPaymentConfirmed}
          label="When payment is received"
          hint="Cash on delivery does not trigger this."
          onChange={() => toggle("sendOnPaymentConfirmed")}
        />
      </div>

      <label className="block space-y-1.5 text-sm font-semibold text-ink">
        <span>Note to add at the end (optional)</span>
        <textarea
          className="form-input min-h-20"
          maxLength={300}
          placeholder="For example: Open 9am to 9pm, call us on 0300 1234567."
          value={form.footerNote}
          onChange={(event) => setForm((current) => ({ ...current, footerNote: event.target.value }))}
        />
      </label>

      <button type="submit" className="ui-btn-primary w-fit" disabled={isSaving}>
        <Save size={16} />
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </Card>
  );
}

function Toggle({ checked, onChange, label, hint, icon: Icon }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-line bg-white px-3 py-2.5">
      <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-brand" checked={checked} onChange={onChange} />
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          {Icon ? <Icon size={14} className="text-brand" /> : null}
          {label}
        </span>
        {hint ? <span className="mt-0.5 block text-xs leading-5 text-muted">{hint}</span> : null}
      </span>
    </label>
  );
}
