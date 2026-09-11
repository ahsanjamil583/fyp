import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { Building2, KeyRound, LockKeyhole, Mail, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { registerBusinessWithEmail, requestBusinessEmailOtp, verifyBusinessEmailOtp } from "../../services/authApi.js";

const schema = Joi.object({
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  otpCode: Joi.string().pattern(/^\d{6}$/).required().label("Verification code").messages({
    "string.pattern.base": "Verification code must be 6 digits.",
  }),
  fullName: Joi.string().min(2).required().label("Full name"),
  businessName: Joi.string().allow("").max(160).label("Business name"),
  password: Joi.string().min(8).required().label("Password"),
});

export function BusinessRegister() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [step, setStep] = useState("email");
  const [sentEmail, setSentEmail] = useState("");
  const [serverError, setServerError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [isVerifyingOtp, setIsVerifyingOtp] = useState(false);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { email: "", otpCode: "", fullName: "", businessName: "", password: "" },
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
      const result = await requestBusinessEmailOtp({ email, purpose: "register" });
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
      await verifyBusinessEmailOtp({ email, code, purpose: "register" });
      setStep("account");
      setStatusMessage("Email verified. Complete your account details.");
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
      const session = await registerBusinessWithEmail({
        email: values.email,
        code: values.otpCode,
        fullName: values.fullName,
        password: values.password,
        ...(values.businessName ? { businessName: values.businessName } : {}),
      });
      setSession(session);
      navigate("/dashboard/business");
    } catch (error) {
      const message = getApiErrorMessage(error, "Registration failed.");
      if (error?.response?.status === 401 || /invalid verification code/i.test(message)) {
        setServerError("Invalid verification code.");
      } else if (error?.response?.status === 410 || /expired/i.test(message)) {
        setServerError("Verification code expired. Please request a new one.");
      } else if (error?.response?.status === 409 || /already registered/i.test(message)) {
        setServerError("This email is already registered. Please login.");
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-[1fr_520px]">
      <AuthHero />
      <section className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md rounded-xl border border-line bg-white p-7 shadow-soft">
          <div className="mb-7">
            <div className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-brand/10 text-brand">
              <Building2 size={22} />
            </div>
            <h2 className="text-2xl font-semibold text-ink">Create Business Account</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Verify your email with a 6-digit code, then create your BizXusAI business workspace.
            </p>
          </div>

          {serverError ? <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}
          {statusMessage ? (
            <div className="mb-4 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
              {statusMessage}
              {otpInfo?.debugCode ? <div className="mt-1 font-semibold">Demo OTP: {otpInfo.debugCode}</div> : null}
              {otpInfo?.demoNote ? <div className="mt-1 text-xs">{otpInfo.demoNote}</div> : null}
            </div>
          ) : null}

          <StepProgress step={step} />

          <form className="space-y-4" onSubmit={(event) => event.preventDefault()}>
            {step === "email" ? (
              <>
                <Field icon={<Mail size={17} />} label="Email" error={form.formState.errors.email?.message}>
                  <input {...form.register("email")} className="auth-input" placeholder="you@company.com" />
                </Field>
                <button type="button" onClick={sendCode} disabled={isSendingOtp} className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60">
                  {isSendingOtp ? "Sending..." : "Send Verification Code"}
                </button>
              </>
            ) : null}

            {step === "code" ? (
              <>
                <div className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-muted">
                  Code sent to <span className="font-semibold text-ink">{otpInfo?.maskedEmail || sentEmail}</span>
                </div>
                <Field icon={<KeyRound size={17} />} label="Verification code" error={form.formState.errors.otpCode?.message}>
                  <input {...form.register("otpCode")} className="auth-input" placeholder="123456" inputMode="numeric" />
                </Field>
                <button type="button" onClick={verifyCode} disabled={isVerifyingOtp} className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60">
                  {isVerifyingOtp ? "Verifying..." : "Verify Code"}
                </button>
                <button type="button" onClick={sendCode} disabled={isSendingOtp || cooldownRemaining > 0} className="w-full rounded-xl border border-line px-4 py-3 text-sm font-semibold text-ink transition hover:border-brand hover:text-brand disabled:opacity-60">
                  {cooldownRemaining > 0 ? `Resend Code in ${cooldownRemaining}s` : isSendingOtp ? "Sending..." : "Resend Code"}
                </button>
              </>
            ) : null}

            {step === "account" ? (
              <>
                <Field icon={<UserRound size={17} />} label="Full name" error={form.formState.errors.fullName?.message}>
                  <input {...form.register("fullName")} className="auth-input" placeholder="Ahsan Jamil" />
                </Field>
                <Field icon={<Building2 size={17} />} label="Business name (optional)" error={form.formState.errors.businessName?.message}>
                  <input {...form.register("businessName")} className="auth-input" placeholder="Your business name" />
                </Field>
                <Field icon={<LockKeyhole size={17} />} label="Password" error={form.formState.errors.password?.message}>
                  <input {...form.register("password")} type="password" className="auth-input" placeholder="Minimum 8 characters" />
                </Field>
                <button type="button" onClick={form.handleSubmit(submit)} disabled={form.formState.isSubmitting} className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60">
                  {form.formState.isSubmitting ? "Please wait..." : "Create account"}
                </button>
              </>
            ) : null}
          </form>

          <div className="mt-6 text-center text-sm text-muted">
            Already registered? <Link className="font-semibold text-brand hover:text-brand-700" to="/login">Login here</Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function AuthHero() {
  return (
    <section className="hidden border-r border-line bg-ink p-10 text-white lg:flex lg:flex-col lg:justify-between">
      <div>
        <BrandLogo showWordmark={false} className="rounded-[1.6rem] border border-white/14 bg-white/6 p-2" imageClassName="h-16 w-16 rounded-[1.1rem] bg-white/88 p-1.5 object-contain" />
        <h1 className="mt-10 max-w-xl text-4xl font-semibold leading-tight">Launch digital storefronts, AI ordering, and business automation from one workspace.</h1>
        <p className="mt-5 max-w-lg text-sm leading-6 text-slate-300">Email-verified onboarding keeps owner accounts simple, professional, and ready for local demo or SMTP production setup.</p>
      </div>
      <div className="grid grid-cols-3 gap-3 text-sm">
        <HeroTile title="Email OTP" text="Verified owner registration" />
        <HeroTile title="AI Commerce" text="Smart ordering and catalog flows" />
        <HeroTile title="Unified CRM" text="Customers, payments, and reports" />
      </div>
    </section>
  );
}

function StepProgress({ step }) {
  const steps = [
    { code: "email", label: "Step 1", title: "Verify Email" },
    { code: "code", label: "Step 2", title: "Enter Code" },
    { code: "account", label: "Step 3", title: "Create Account" },
  ];
  const activeIndex = steps.findIndex((item) => item.code === step);

  return (
    <div className="mb-5 grid gap-2 sm:grid-cols-3">
      {steps.map((item, index) => {
        const isDone = index < activeIndex;
        const isActive = index === activeIndex;
        return (
          <div
            key={item.code}
            className={
              isActive
                ? "rounded-xl border border-brand bg-brand-50 px-3 py-2"
                : isDone
                  ? "rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2"
                  : "rounded-xl border border-line bg-surface px-3 py-2"
            }
          >
            <div className={isActive ? "text-[11px] font-bold uppercase tracking-wide text-brand" : isDone ? "text-[11px] font-bold uppercase tracking-wide text-emerald-700" : "text-[11px] font-bold uppercase tracking-wide text-muted"}>
              {item.label}
            </div>
            <div className="mt-1 text-xs font-semibold text-ink">{item.title}</div>
          </div>
        );
      })}
    </div>
  );
}

function HeroTile({ title, text }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="font-semibold">{title}</div>
      <div className="mt-1 text-slate-300">{text}</div>
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
