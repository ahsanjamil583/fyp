import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { KeyRound, LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { requestBusinessEmailPasswordResetOtp, resetBusinessPasswordWithEmailOtp } from "../../services/authApi.js";
import { requestCustomerEmailPasswordResetOtp, resetCustomerPasswordWithEmailOtp } from "../../services/customerAuthApi.js";
import { AuthAlert, AuthField, AuthLayout, AuthSubmit } from "./AuthLayout.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

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
    <AuthLayout
      audience={customer ? "customer" : "business"}
      icon={KeyRound}
      title="Reset your password"
      subtitle="Enter your registered email, receive a 6-digit code, then set a new password."
    >
      <AuthAlert tone="red">{serverError}</AuthAlert>
      <AuthAlert tone="green">
        {statusMessage}
        {statusMessage && otpInfo?.expiresInSeconds ? (
          <div className="mt-1 text-xs font-medium">
            {otpInfo.codeLength || 6} digits, expires in about {Math.ceil(otpInfo.expiresInSeconds / 60)} minute(s).
          </div>
        ) : null}
      </AuthAlert>

      <form className="space-y-4" onSubmit={form.handleSubmit(submit)} noValidate>
        <AuthField icon={<Mail size={17} />} label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
          <input id="email" {...form.register("email")} type="email" className="auth-input" placeholder="you@company.pk" autoComplete="email" aria-invalid={Boolean(form.formState.errors.email)} />
        </AuthField>

        <div className="grid grid-cols-[1fr_auto] items-end gap-2">
          <AuthField icon={<KeyRound size={17} />} label="Reset code" htmlFor="otpCode" error={form.formState.errors.otpCode?.message}>
            <input id="otpCode" {...form.register("otpCode")} className="auth-input tracking-[0.3em]" placeholder="6-digit code" inputMode="numeric" autoComplete="one-time-code" aria-invalid={Boolean(form.formState.errors.otpCode)} />
          </AuthField>
          <button type="button" onClick={sendOtp} disabled={isSendingOtp} className="ui-btn-secondary !py-3 whitespace-nowrap">
            {isSendingOtp ? "Sending..." : "Send code"}
          </button>
        </div>

        <AuthField icon={<LockKeyhole size={17} />} label="New password" htmlFor="newPassword" error={form.formState.errors.newPassword?.message}>
          <input id="newPassword" {...form.register("newPassword")} type="password" className="auth-input" placeholder="Minimum 8 characters" autoComplete="new-password" aria-invalid={Boolean(form.formState.errors.newPassword)} />
        </AuthField>

        <AuthSubmit isSubmitting={form.formState.isSubmitting}>Reset password</AuthSubmit>
      </form>

      <div className="mt-5 border-t border-line-soft pt-5 text-center text-sm text-muted">
        <Link className="font-bold text-brand hover:text-brand-hover" to={customer ? "/customer/login" : "/login"}>
          Back to login
        </Link>
      </div>
    </AuthLayout>
  );
}
