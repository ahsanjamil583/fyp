import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { KeyRound, LockKeyhole, Mail, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCustomerMe, registerCustomer, requestCustomerEmailOtp, verifyCustomerEmailOtp } from "../../services/customerAuthApi.js";
import { AuthAlert, AuthField, AuthFooterLinks, AuthLayout, AuthStepper, AuthSubmit } from "../auth/AuthLayout.jsx";

const schema = Joi.object({
  fullName: Joi.string().min(2).required().label("Full name"),
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  otpCode: Joi.string().pattern(/^\d{6}$/).required().label("Verification code").messages({
    "string.pattern.base": "Verification code must be 6 digits.",
  }),
  password: Joi.string().min(8).required().label("Password"),
});

const STEPS = [
  { code: "email", label: "Verify email" },
  { code: "code", label: "Enter code" },
  { code: "account", label: "Create account" },
];

export function CustomerRegister() {
  const navigate = useNavigate();
  const { setCustomerSession } = useCustomer();
  const [step, setStep] = useState("email");
  const [sentEmail, setSentEmail] = useState("");
  const [serverError, setServerError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const [isVerifyingOtp, setIsVerifyingOtp] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { fullName: "", email: "", otpCode: "", password: "" },
  });
  const watchedEmail = form.watch("email");

  useEffect(() => {
    if (!sentEmail || !watchedEmail || watchedEmail.trim().toLowerCase() === sentEmail) return;
    setStep("email");
    setOtpInfo(null);
    setStatusMessage("");
    form.setValue("otpCode", "");
  }, [form, sentEmail, watchedEmail]);

  useEffect(() => {
    if (!cooldownRemaining) return undefined;
    const timer = window.setInterval(() => {
      setCooldownRemaining((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownRemaining]);

  async function sendCode() {
    setServerError("");
    setStatusMessage("");
    const email = form.getValues("email");
    const emailError = Joi.string().email({ tlds: false }).required().validate(email).error;
    if (emailError) {
      setServerError("Enter a valid email address first.");
      return;
    }

    setIsSendingOtp(true);
    try {
      const result = await requestCustomerEmailOtp({ email, purpose: "register" });
      setOtpInfo(result);
      setSentEmail(email.trim().toLowerCase());
      setCooldownRemaining(result.resendCooldownSeconds || 0);
      setStep("code");
      setStatusMessage("Verification code sent to your email.");
    } catch (error) {
      const message = getApiErrorMessage(error, "Could not send verification code.");
      if (error?.response?.status === 409 || /already registered/i.test(message)) {
        setServerError("This email is already registered. Please login.");
      } else if (error?.response?.status === 429) {
        setServerError(message || "Please wait before requesting another code.");
      } else {
        setServerError(message || "Unable to send verification code. Please try again.");
      }
    } finally {
      setIsSendingOtp(false);
    }
  }

  async function verifyCode() {
    setServerError("");
    setStatusMessage("");
    const email = form.getValues("email");
    const code = form.getValues("otpCode");
    if (!otpInfo) {
      setServerError("Send the verification code first.");
      return;
    }
    if (!/^\d{6}$/.test(String(code || ""))) {
      setServerError("Enter the 6-digit verification code.");
      return;
    }

    setIsVerifyingOtp(true);
    try {
      await verifyCustomerEmailOtp({ email, code, purpose: "register" });
      setStep("account");
      setStatusMessage("Email verified. Now set your account details.");
    } catch (error) {
      const message = getApiErrorMessage(error, "Verification failed.");
      if (error?.response?.status === 401 || /invalid verification code/i.test(message)) {
        setServerError("Invalid verification code.");
      } else if (error?.response?.status === 410 || /expired/i.test(message)) {
        setServerError("Verification code expired. Please request a new one.");
      } else {
        setServerError(message);
      }
    } finally {
      setIsVerifyingOtp(false);
    }
  }

  async function submit(values) {
    setServerError("");
    setStatusMessage("");
    if (step !== "account") {
      setServerError("Please verify your email first.");
      return;
    }
    try {
      const session = await registerCustomer({
        fullName: values.fullName,
        email: values.email,
        code: values.otpCode,
        password: values.password,
      });
      setCustomerSession(session);
      const me = await getCustomerMe();
      setCustomerSession({ ...session, profile: me.profile });
      navigate("/customer/marketplace");
    } catch (error) {
      const message = getApiErrorMessage(error, "Registration failed.");
      if (error?.response?.status === 401 || /invalid verification code/i.test(message)) {
        setServerError("Invalid verification code.");
      } else if (error?.response?.status === 410 || /expired/i.test(message)) {
        setServerError("Verification code expired. Please request a new one.");
      } else if (error?.response?.status === 409 || /already exists|already registered/i.test(message)) {
        setServerError("A customer account already exists with this email. Sign in, or reset the password if you forgot it.");
      } else {
        setServerError(message);
      }
    }
  }

  const activeIndex = STEPS.findIndex((s) => s.code === step);

  return (
    <AuthLayout
      audience="customer"
      icon={UserRound}
      title="Create your customer account"
      subtitle="Verify your email and start ordering from local businesses."
      footer={<AuthFooterLinks audience="customer" />}
    >
      <AuthStepper steps={STEPS} activeIndex={activeIndex} />

      <AuthAlert tone="red">{serverError}</AuthAlert>
      <AuthAlert tone="green">{statusMessage}</AuthAlert>

      <form className="space-y-4" onSubmit={(event) => event.preventDefault()} noValidate>
        {step === "email" ? (
          <>
            <AuthField icon={<Mail size={17} />} label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
              <input id="email" {...form.register("email")} type="email" className="auth-input" placeholder="you@company.pk" autoComplete="email" aria-invalid={Boolean(form.formState.errors.email)} />
            </AuthField>
            <AuthSubmit type="button" onClick={sendCode} isSubmitting={isSendingOtp}>
              Send verification code
            </AuthSubmit>
          </>
        ) : null}

        {step === "code" ? (
          <>
            <div className="rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-muted">
              Code sent to <span className="font-bold text-ink">{otpInfo?.maskedEmail || sentEmail}</span>
            </div>
            <AuthField icon={<KeyRound size={17} />} label="Verification code" htmlFor="otpCode" error={form.formState.errors.otpCode?.message}>
              <input id="otpCode" {...form.register("otpCode")} className="auth-input tracking-[0.3em]" placeholder="6-digit code" inputMode="numeric" autoComplete="one-time-code" aria-invalid={Boolean(form.formState.errors.otpCode)} />
            </AuthField>
            <AuthSubmit type="button" onClick={verifyCode} isSubmitting={isVerifyingOtp}>
              Verify code
            </AuthSubmit>
            <button
              type="button"
              onClick={sendCode}
              disabled={isSendingOtp || cooldownRemaining > 0}
              className="ui-btn-secondary w-full !py-3"
            >
              {cooldownRemaining > 0 ? `Resend code in ${cooldownRemaining}s` : isSendingOtp ? "Sending..." : "Resend code"}
            </button>
          </>
        ) : null}

        {step === "account" ? (
          <>
            <AuthField icon={<UserRound size={17} />} label="Full name" htmlFor="fullName" error={form.formState.errors.fullName?.message}>
              <input id="fullName" {...form.register("fullName")} className="auth-input" placeholder="Ahsan Jamil" autoComplete="name" aria-invalid={Boolean(form.formState.errors.fullName)} />
            </AuthField>
            <AuthField icon={<LockKeyhole size={17} />} label="Password" htmlFor="password" error={form.formState.errors.password?.message}>
              <input id="password" {...form.register("password")} type="password" className="auth-input" placeholder="Minimum 8 characters" autoComplete="new-password" aria-invalid={Boolean(form.formState.errors.password)} />
            </AuthField>
            <AuthSubmit type="button" onClick={form.handleSubmit(submit)} isSubmitting={form.formState.isSubmitting}>
              Create account
            </AuthSubmit>
          </>
        ) : null}
      </form>

      <div className="mt-5 border-t border-line-soft pt-5 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link className="font-bold text-brand hover:text-brand-hover" to="/customer/login">
          Log in
        </Link>
      </div>
    </AuthLayout>
  );
}
