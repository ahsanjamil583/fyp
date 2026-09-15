import { AlertTriangle, CheckCircle2, Loader2, Mail, ShieldCheck, Smartphone, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { getApiErrorMessage } from "../../services/apiError.js";
import {
  resendWalletOtpCheckout,
  startWalletOtpCheckout,
  verifyWalletOtpCheckout,
} from "../../services/customerPortalApi.js";

/**
 * The emailed-code payment step.
 *
 * Two screens in one dialog: enter the wallet mobile number, then enter the code that
 * arrives by email. The amount shown is the one the server computed from the order - the
 * dialog never sends an amount, and never receives a code.
 *
 * Every failure the API can return is surfaced verbatim, because each one tells the
 * customer something different and actionable: wrong code and attempts left, expired,
 * locked out, cooldown, or no email on the profile.
 */

const STEP_MOBILE = "mobile";
const STEP_CODE = "code";
const STEP_DONE = "done";

function formatMoney(amount, currency = "PKR") {
  return `${currency} ${Number(amount || 0).toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function useCountdown(targetIso) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (!targetIso) {
      setRemaining(0);
      return undefined;
    }
    function tick() {
      const seconds = Math.max(0, Math.floor((new Date(targetIso).getTime() - Date.now()) / 1000));
      setRemaining(seconds);
    }
    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => window.clearInterval(intervalId);
  }, [targetIso]);

  return remaining;
}

export function WalletOtpDialog({ order, method, customerEmail, onClose, onPaid }) {
  const [step, setStep] = useState(STEP_MOBILE);
  const [mobileNumber, setMobileNumber] = useState("");
  const [code, setCode] = useState("");
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [resendAvailableAt, setResendAvailableAt] = useState(null);
  const codeInputRef = useRef(null);

  const expiresIn = useCountdown(session?.expiresAt);
  const resendIn = useCountdown(resendAvailableAt);
  const hasEmail = Boolean(String(customerEmail || "").trim());

  useEffect(() => {
    if (step === STEP_CODE && codeInputRef.current) {
      codeInputRef.current.focus();
    }
  }, [step]);

  useEffect(() => {
    function handleEscape(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const applySession = useCallback((data) => {
    setSession(data);
    setResendAvailableAt(new Date(Date.now() + (data.resendCooldownSeconds || 0) * 1000).toISOString());
  }, []);

  async function submitMobile(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsBusy(true);
    try {
      const data = await startWalletOtpCheckout(order.id, method.code, mobileNumber);
      applySession(data);
      setStep(STEP_CODE);
      setNotice(`We emailed a ${data.codeLength}-digit code to ${data.maskedEmail}.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not start this payment."));
    } finally {
      setIsBusy(false);
    }
  }

  async function submitCode(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsBusy(true);
    try {
      const result = await verifyWalletOtpCheckout(order.id, session.paymentRecordId, code);
      setStep(STEP_DONE);
      onPaid?.(result);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not confirm this payment."));
      setCode("");
      codeInputRef.current?.focus();
    } finally {
      setIsBusy(false);
    }
  }

  async function resend() {
    setError("");
    setNotice("");
    setIsBusy(true);
    try {
      const data = await resendWalletOtpCheckout(order.id, session.paymentRecordId);
      applySession(data);
      setCode("");
      setNotice(`A new code was emailed to ${data.maskedEmail}. The previous code no longer works.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not send a new code."));
    } finally {
      setIsBusy(false);
    }
  }

  const amount = session?.amount ?? order?.paymentSummary?.balance ?? order?.pricing?.total;
  const currency = session?.currency || order?.pricing?.currency || "PKR";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${method.label} payment`}
        className="max-h-full w-full max-w-md overflow-y-auto rounded-t-card bg-white shadow-lift sm:rounded-card"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">{method.label}</div>
            <h2 className="mt-1 text-lg font-extrabold text-ink">
              {step === STEP_DONE ? "Payment confirmed" : `Pay ${formatMoney(amount, currency)}`}
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted">Order {order.transactionNumber}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line text-muted transition hover:bg-surface hover:text-ink"
          >
            <X size={16} />
          </button>
        </header>

        <div className="space-y-4 px-5 py-5">
          <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs font-semibold leading-5 text-amber-800">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>Simulated payment for demonstration. No real money is transferred.</span>
          </div>

          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-semibold text-red-700">{error}</div>
          ) : null}
          {notice && !error ? (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2.5 text-sm font-semibold text-blue-700">{notice}</div>
          ) : null}

          {/* ------------------------------------------------ step 1: mobile -- */}
          {step === STEP_MOBILE ? (
            !hasEmail ? (
              <div className="space-y-3">
                <div className="flex items-start gap-2 rounded-xl border border-orange-200 bg-orange-100 px-3 py-3 text-sm font-semibold leading-6 text-orange-800">
                  <Mail size={16} className="mt-0.5 shrink-0" />
                  Please add an email to your profile to pay this way.
                </div>
                <a href="/customer/profile" className="ui-btn-primary w-full">
                  Open profile settings
                </a>
                <button type="button" onClick={onClose} className="ui-btn-secondary w-full">
                  Choose another method
                </button>
              </div>
            ) : (
              <form className="space-y-4" onSubmit={submitMobile}>
                <label className="block space-y-1.5 text-sm font-semibold text-ink">
                  <span>Your {method.label} mobile number</span>
                  <span className="relative block">
                    <Smartphone size={17} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
                    <input
                      className="form-input pl-10 text-base tracking-wide"
                      inputMode="tel"
                      autoComplete="tel"
                      placeholder="03001234567"
                      required
                      value={mobileNumber}
                      onChange={(event) => setMobileNumber(event.target.value)}
                    />
                  </span>
                </label>
                <p className="flex items-start gap-2 text-xs leading-5 text-muted">
                  <Mail size={14} className="mt-0.5 shrink-0" />
                  We will email a confirmation code to <strong className="font-bold text-ink">{customerEmail}</strong>.
                </p>
                <button type="submit" className="ui-btn-primary w-full py-3.5 text-base" disabled={isBusy}>
                  {isBusy ? <Loader2 size={18} className="animate-spin" /> : <ShieldCheck size={18} />}
                  {isBusy ? "Sending code..." : `Pay ${formatMoney(amount, currency)}`}
                </button>
              </form>
            )
          ) : null}

          {/* -------------------------------------------------- step 2: code -- */}
          {step === STEP_CODE && session ? (
            <form className="space-y-4" onSubmit={submitCode}>
              <label className="block space-y-1.5 text-sm font-semibold text-ink">
                <span>Enter the {session.codeLength}-digit code</span>
                <input
                  ref={codeInputRef}
                  className="form-input text-center text-2xl font-extrabold tracking-[0.5em]"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={session.codeLength}
                  placeholder={"0".repeat(session.codeLength)}
                  required
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                />
              </label>

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-muted">
                <span>
                  {expiresIn > 0 ? (
                    <>
                      Expires in{" "}
                      <span className="font-extrabold text-ink">
                        {Math.floor(expiresIn / 60)}:{String(expiresIn % 60).padStart(2, "0")}
                      </span>
                    </>
                  ) : (
                    <span className="font-extrabold text-red-600">This code has expired.</span>
                  )}
                </span>
                <span>{session.attemptsRemaining} attempt{session.attemptsRemaining === 1 ? "" : "s"} left</span>
              </div>

              <button
                type="submit"
                className="ui-btn-primary w-full py-3.5 text-base"
                disabled={isBusy || code.length !== session.codeLength || expiresIn <= 0}
              >
                {isBusy ? <Loader2 size={18} className="animate-spin" /> : <ShieldCheck size={18} />}
                {isBusy ? "Confirming..." : "Confirm payment"}
              </button>

              <div className="flex items-center justify-between gap-2 border-t border-line-soft pt-3">
                <button
                  type="button"
                  className="text-sm font-bold text-brand disabled:text-muted"
                  onClick={resend}
                  disabled={isBusy || resendIn > 0 || session.resendsRemaining <= 0}
                >
                  {session.resendsRemaining <= 0
                    ? "No resends left"
                    : resendIn > 0
                      ? `Resend in ${resendIn}s`
                      : "Send a new code"}
                </button>
                <button type="button" className="text-sm font-semibold text-muted" onClick={onClose}>
                  Cancel
                </button>
              </div>
            </form>
          ) : null}

          {/* --------------------------------------------------- step 3: done -- */}
          {step === STEP_DONE ? (
            <div className="space-y-4 text-center">
              <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-green-50">
                <CheckCircle2 size={32} className="text-green-600" />
              </div>
              <div>
                <p className="text-base font-extrabold text-ink">{formatMoney(amount, currency)} paid</p>
                <p className="mt-1 text-sm text-muted">Your order is marked as paid. A receipt is available on this page.</p>
              </div>
              <button type="button" className="ui-btn-primary w-full py-3.5" onClick={onClose}>
                Done
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
