import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { KeyRound, LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { requestBusinessEmailPasswordResetOtp, resetBusinessPasswordWithEmailOtp } from "../../services/authApi.js";
import { requestCustomerEmailPasswordResetOtp, resetCustomerPasswordWithEmailOtp } from "../../services/customerAuthApi.js";

const emailSchema = Joi.object({
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  otpCode: Joi.string().pattern(/^\d{6}$/).required().label("Verification code").messages({
    "string.pattern.base": "Verification code must be 6 digits.",
  }),
  newPassword: Joi.string().min(8).required().label("New password"),
});

export function PhonePasswordResetPage({ customer = false }) {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const form = useForm({
    resolver: joiResolver(emailSchema),
    defaultValues: { email: "", otpCode: "", newPassword: "" },
  });

  async function sendOtp() {
    setServerError("");
    setStatusMessage("");
    const identifier = form.getValues("email");
    if (!identifier) {
      setServerError("Enter your email first.");
      return;
    }
    setIsSendingOtp(true);
    try {
      const result = customer
        ? await requestCustomerEmailPasswordResetOtp({ email: identifier, purpose: "password_reset" })
        : await requestBusinessEmailPasswordResetOtp({ email: identifier, purpose: "password_reset" });
      setOtpInfo(result);
      setStatusMessage(`Password reset code sent to ${result.maskedEmail || result.email}.`);
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Could not send password reset code."));
    } finally {
      setIsSendingOtp(false);
    }
  }

  async function submit(values) {
    setServerError("");
    setStatusMessage("");
    try {
      if (customer) {
        await resetCustomerPasswordWithEmailOtp({ email: values.email, code: values.otpCode, newPassword: values.newPassword });
        navigate("/customer/login");
        return;
      }
      await resetBusinessPasswordWithEmailOtp({ email: values.email, code: values.otpCode, newPassword: values.newPassword });
      navigate("/login");
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Password reset failed."));
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 py-10">
      <div className="w-full max-w-md rounded-xl border border-line bg-white p-7 shadow-soft">
        <BrandLogo showWordmark={false} className="mb-5 h-12 w-12 rounded-xl bg-white" imageClassName="h-12 w-12 rounded-xl object-contain" />
        <h1 className="text-2xl font-semibold text-ink">Reset password with email OTP</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Enter your registered email, receive a 6-digit code, and set a new password for your account.
        </p>

        {serverError ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}
        {statusMessage ? (
          <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
            {statusMessage}
            {otpInfo?.debugCode ? <div className="mt-1 font-semibold">Demo OTP: {otpInfo.debugCode}</div> : null}
          </div>
        ) : null}

        <form className="mt-5 space-y-4" onSubmit={form.handleSubmit(submit)}>
          <Field icon={<Mail size={17} />} label="Email" error={form.formState.errors.email?.message}>
            <input {...form.register("email")} className="auth-input" placeholder="you@company.com" />
          </Field>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Field icon={<KeyRound size={17} />} label="OTP code" error={form.formState.errors.otpCode?.message}>
              <input {...form.register("otpCode")} className="auth-input" placeholder="123456" inputMode="numeric" />
            </Field>
            <button type="button" onClick={sendOtp} disabled={isSendingOtp} className="mt-6 rounded-xl border border-line px-3 text-sm font-semibold text-ink hover:border-brand hover:text-brand disabled:opacity-60">
              {isSendingOtp ? "Sending..." : "Send Reset Code"}
            </button>
          </div>
          <Field icon={<LockKeyhole size={17} />} label="New password" error={form.formState.errors.newPassword?.message}>
            <input {...form.register("newPassword")} type="password" className="auth-input" placeholder="Minimum 8 characters" />
          </Field>
          <button type="submit" disabled={form.formState.isSubmitting} className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
            {form.formState.isSubmitting ? "Please wait..." : "Reset password"}
          </button>
        </form>
        <div className="mt-5 text-center text-sm text-muted">
          <Link className="font-semibold text-brand" to={customer ? "/customer/login" : "/login"}>Back to login</Link>
        </div>
      </div>
    </div>
  );
}

function Field({ icon, label, error, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <div className="flex items-center gap-2 rounded-xl border border-line bg-white px-3 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/15">
        <span className="text-muted">{icon}</span>
        {children}
      </div>
      {error ? <span className="mt-1 block text-xs text-red-600">{error}</span> : null}
    </label>
  );
}
