import { Building2, KeyRound, LockKeyhole, Mail, Phone, ShieldCheck, UserRound } from "lucide-react";
import { Link } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";

export function AuthPanel({
  title,
  subtitle,
  mode,
  register,
  errors,
  isSubmitting,
  serverError,
  serverErrorActionTo = "",
  serverErrorActionLabel = "",
  onSubmit,
  submitLabel,
  switchTo,
  switchLabel,
  customer = false,
  authVariant = "password",
  emailOptional = false,
  showPhone = true,
  otpInfo = null,
  otpStatus = "",
  onSendOtp,
  isSendingOtp = false,
  onToggleAuthVariant,
  authVariantToggleLabel = "",
  passwordResetTo = "",
}) {
  const isPhoneOtp = authVariant === "phoneOtp";
  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-[1fr_520px]">
      <section className="hidden border-r border-line bg-ink p-10 text-white lg:flex lg:flex-col lg:justify-between">
        <div>
          <BrandLogo
            showWordmark={false}
            className="rounded-[1.6rem] border border-white/14 bg-white/6 p-2 shadow-[0_20px_40px_rgba(11,21,48,0.30)] backdrop-blur"
            imageClassName="h-16 w-16 rounded-[1.1rem] border border-white/18 bg-white/88 p-1.5 object-contain shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]"
          />
          <h1 className="mt-10 max-w-xl text-4xl font-semibold leading-tight">
            Launch digital storefronts, customer journeys, and AI-assisted business operations from one SaaS platform.
          </h1>
          <p className="mt-5 max-w-lg text-sm leading-6 text-slate-300">
            Built for modern businesses that want automated websites, customer management, smart ordering flows, and PKR-ready operations with a polished multi-role workspace.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold">Verified Access</div>
            <div className="mt-1 text-slate-300">Email OTP registration for owners</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold">Unified Workspace</div>
            <div className="mt-1 text-slate-300">Storefront, CRM, analytics, and operations</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold">AI Commerce</div>
            <div className="mt-1 text-slate-300">Smarter ordering and customer engagement</div>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md rounded-xl border border-line bg-white p-7 shadow-soft">
          <div className="mb-7">
            <div className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-brand/10 text-brand">
              {customer ? <UserRound size={22} /> : <Building2 size={22} />}
            </div>
            <h2 className="text-2xl font-semibold text-ink">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">{subtitle}</p>
          </div>

          {onToggleAuthVariant ? (
            <button
              type="button"
              onClick={onToggleAuthVariant}
              className="mb-4 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink transition hover:border-brand hover:text-brand"
            >
              {authVariantToggleLabel || (isPhoneOtp ? "Use email + password instead" : "Use phone OTP instead")}
            </button>
          ) : null}

          {serverError ? (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {serverError}
              {serverErrorActionTo && serverErrorActionLabel ? (
                <Link className="ml-1 font-semibold text-red-800 underline" to={serverErrorActionTo}>
                  {serverErrorActionLabel}
                </Link>
              ) : null}
            </div>
          ) : null}

          {isPhoneOtp && !otpInfo ? (
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Step 1: enter your phone number and click Send OTP. Step 2: enter the code and continue. Demo code is usually 123456 after Send OTP.
            </div>
          ) : null}

          {otpStatus ? (
            <div className="mb-4 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
              {otpStatus}
              {otpInfo?.debugCode ? (
                <div className="mt-1 font-semibold">Demo OTP: {otpInfo.debugCode}</div>
              ) : null}
              {otpInfo?.expiresInSeconds ? (
                <div className="mt-1 text-xs">
                  Code length: {otpInfo.codeLength || 6} digits. Expires in about {Math.ceil(otpInfo.expiresInSeconds / 60)} minute(s).
                  {otpInfo.resendCooldownSeconds ? ` Resend cooldown: ${otpInfo.resendCooldownSeconds}s.` : ""}
                </div>
              ) : null}
            </div>
          ) : null}

          <form className="space-y-4" onSubmit={onSubmit}>
            {mode === "register" ? (
              <Field icon={<UserRound size={17} />} label="Full name" error={errors.fullName?.message}>
                <input {...register("fullName")} className="auth-input" placeholder="Ahsan Jamil" />
              </Field>
            ) : null}

            {(showPhone && mode === "register") || isPhoneOtp ? (
              <Field icon={<Phone size={17} />} label="Phone" error={errors.phone?.message}>
                <input {...register("phone")} className="auth-input" placeholder="03001234567 or +923001234567" />
              </Field>
            ) : null}

            {mode === "register" || !isPhoneOtp ? (
              <Field icon={<Mail size={17} />} label={emailOptional ? "Email (optional)" : "Email"} error={errors.email?.message}>
                <input {...register("email")} className="auth-input" placeholder={emailOptional ? "Optional email" : "you@company.pk"} />
              </Field>
            ) : null}

            {isPhoneOtp ? (
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <Field icon={<KeyRound size={17} />} label="OTP code" error={errors.otpCode?.message}>
                  <input {...register("otpCode")} className="auth-input disabled:bg-surface disabled:text-muted" placeholder={otpInfo ? "123456" : "Send OTP first"} disabled={!otpInfo} />
                </Field>
                <button
                  type="button"
                  onClick={onSendOtp}
                  disabled={isSendingOtp}
                  className="mt-6 rounded-xl border border-line px-3 text-sm font-semibold text-ink transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSendingOtp ? "Sending..." : "Send OTP"}
                </button>
              </div>
            ) : null}

            {mode === "register" || !isPhoneOtp ? (
              <Field icon={<LockKeyhole size={17} />} label="Password" error={errors.password?.message}>
                <input {...register("password")} type="password" className="auth-input" placeholder="Minimum 8 characters" />
              </Field>
            ) : null}

            {mode === "register" && isPhoneOtp ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs leading-5 text-emerald-800">
                <div className="flex items-center gap-2 font-semibold"><ShieldCheck size={15} /> Phone-first onboarding</div>
                <div className="mt-1">Your phone number is verified before account creation, matching the BizXusAI proposal flow for Pakistani SMEs.</div>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Please wait..." : submitLabel}
            </button>
          </form>

          {passwordResetTo ? (
            <div className="mt-4 text-center text-sm">
              <Link className="font-semibold text-brand hover:text-brand-700" to={passwordResetTo}>
                Forgot password? Reset password
              </Link>
            </div>
          ) : null}

          <div className="mt-6 text-center text-sm text-muted">
            {switchLabel}{" "}
            <Link className="font-semibold text-brand hover:text-brand-700" to={switchTo}>
              Continue here
            </Link>
          </div>

          <div className="mt-4 rounded-xl bg-surface p-4 text-sm text-muted">
            {customer ? (
              <div className="space-y-2 text-center">
                <div>Business owner or admin?</div>
                <Link className="font-semibold text-brand hover:text-brand-700" to="/login">
                  Go to business login
                </Link>
              </div>
            ) : (
              <div className="space-y-2 text-center">
                <div>Customer account?</div>
                <div className="flex items-center justify-center gap-3">
                  <Link className="font-semibold text-brand hover:text-brand-700" to="/customer/login">
                    Customer login
                  </Link>
                  <span className="text-line">|</span>
                  <Link className="font-semibold text-brand hover:text-brand-700" to="/customer/register">
                    Customer register
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
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
