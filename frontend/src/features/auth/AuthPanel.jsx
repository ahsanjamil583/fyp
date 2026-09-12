import { Building2, KeyRound, LockKeyhole, Mail, Phone, UserRound } from "lucide-react";
import { Link } from "react-router-dom";

import { AuthAlert, AuthField, AuthFooterLinks, AuthLayout, AuthSubmit } from "./AuthLayout.jsx";

/**
 * Login/register form rendered inside the shared auth shell.
 *
 * The props are unchanged so existing call sites keep working. What is gone: the
 * "Demo OTP: 123456" readout and the phone-first onboarding notice. Printing a live
 * one-time code into the page is fine on a laptop and not fine on a public demo URL,
 * and business sign-in is email/password only now.
 */
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
  const audience = customer ? "customer" : "business";

  return (
    <AuthLayout
      audience={audience}
      icon={customer ? UserRound : Building2}
      title={title}
      subtitle={subtitle}
      footer={<AuthFooterLinks audience={audience} />}
    >
      {onToggleAuthVariant ? (
        <button
          type="button"
          onClick={onToggleAuthVariant}
          className="ui-btn-secondary mb-4 w-full"
        >
          {authVariantToggleLabel || (isPhoneOtp ? "Use email + password instead" : "Use a one-time code instead")}
        </button>
      ) : null}

      <AuthAlert tone="red" actionTo={serverErrorActionTo} actionLabel={serverErrorActionLabel}>
        {serverError}
      </AuthAlert>

      {isPhoneOtp && !otpInfo ? (
        <AuthAlert tone="brand">Enter your phone number and send the code, then type it in below.</AuthAlert>
      ) : null}

      {otpStatus ? (
        <AuthAlert tone="green">
          {otpStatus}
          {otpInfo?.expiresInSeconds ? (
            <div className="mt-1 text-xs font-medium">
              {otpInfo.codeLength || 6} digits, expires in about {Math.ceil(otpInfo.expiresInSeconds / 60)} minute(s).
              {otpInfo.resendCooldownSeconds ? ` You can resend after ${otpInfo.resendCooldownSeconds}s.` : ""}
            </div>
          ) : null}
        </AuthAlert>
      ) : null}

      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        {mode === "register" ? (
          <AuthField icon={<UserRound size={17} />} label="Full name" htmlFor="fullName" error={errors.fullName?.message}>
            <input
              id="fullName"
              {...register("fullName")}
              className="auth-input"
              placeholder="Ahsan Jamil"
              autoComplete="name"
              aria-invalid={Boolean(errors.fullName)}
            />
          </AuthField>
        ) : null}

        {(showPhone && mode === "register") || isPhoneOtp ? (
          <AuthField icon={<Phone size={17} />} label="Phone" htmlFor="phone" error={errors.phone?.message}>
            <input
              id="phone"
              {...register("phone")}
              className="auth-input"
              placeholder="03001234567"
              autoComplete="tel"
              inputMode="tel"
              aria-invalid={Boolean(errors.phone)}
            />
          </AuthField>
        ) : null}

        {mode === "register" || !isPhoneOtp ? (
          <AuthField
            icon={<Mail size={17} />}
            label={emailOptional ? "Email (optional)" : "Email"}
            htmlFor="email"
            error={errors.email?.message}
          >
            <input
              id="email"
              {...register("email")}
              type="email"
              className="auth-input"
              placeholder="you@company.pk"
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
            />
          </AuthField>
        ) : null}

        {isPhoneOtp ? (
          <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
            <AuthField icon={<KeyRound size={17} />} label="Verification code" htmlFor="otpCode" error={errors.otpCode?.message}>
              <input
                id="otpCode"
                {...register("otpCode")}
                className="auth-input disabled:bg-surface disabled:text-subtle"
                placeholder={otpInfo ? "6-digit code" : "Send the code first"}
                disabled={!otpInfo}
                autoComplete="one-time-code"
                inputMode="numeric"
                aria-invalid={Boolean(errors.otpCode)}
              />
            </AuthField>
            <button
              type="button"
              onClick={onSendOtp}
              disabled={isSendingOtp}
              className="ui-btn-secondary !py-3 whitespace-nowrap"
            >
              {isSendingOtp ? "Sending..." : "Send code"}
            </button>
          </div>
        ) : null}

        {mode === "register" || !isPhoneOtp ? (
          <AuthField icon={<LockKeyhole size={17} />} label="Password" htmlFor="password" error={errors.password?.message}>
            <input
              id="password"
              {...register("password")}
              type="password"
              className="auth-input"
              placeholder="Minimum 8 characters"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              aria-invalid={Boolean(errors.password)}
            />
          </AuthField>
        ) : null}

        <AuthSubmit isSubmitting={isSubmitting}>{submitLabel}</AuthSubmit>
      </form>

      {passwordResetTo ? (
        <div className="mt-4 text-center">
          <Link className="text-sm font-bold text-brand hover:text-brand-hover" to={passwordResetTo}>
            Forgot your password?
          </Link>
        </div>
      ) : null}

      <div className="mt-5 border-t border-line-soft pt-5 text-center text-sm text-muted">
        {switchLabel}{" "}
        <Link className="font-bold text-brand hover:text-brand-hover" to={switchTo}>
          Continue here
        </Link>
      </div>
    </AuthLayout>
  );
}
