import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { LockKeyhole, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { changeBusinessPassword } from "../../services/authApi.js";
import { changeCustomerPassword } from "../../services/customerAuthApi.js";

const schema = Joi.object({
  currentPassword: Joi.string().required().label("Current password"),
  newPassword: Joi.string().min(8).required().label("New password"),
  confirmPassword: Joi.string().required().valid(Joi.ref("newPassword")).label("Confirm password").messages({
    "any.only": "Passwords do not match.",
  }),
});

/**
 * Shown when the API reports `password_reset_required`, which happens when a
 * sign-in succeeds with a password that fails the current strength policy. The
 * account stays blocked from every other endpoint until this form succeeds.
 */
export function ForcedPasswordResetPage({ customer = false }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const customerSession = useCustomer();
  const [serverError, setServerError] = useState("");
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  async function submit(values) {
    setServerError("");
    const payload = { currentPassword: values.currentPassword, newPassword: values.newPassword };
    try {
      if (customer) {
        const session = await changeCustomerPassword(payload);
        customerSession.setCustomerSession(session);
        navigate("/customer/marketplace", { replace: true });
        return;
      }
      const session = await changeBusinessPassword(payload);
      auth.setSession(session);
      navigate("/dashboard", { replace: true });
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Could not update your password."));
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4 py-10">
      <div className="w-full max-w-md rounded-md border border-line bg-white p-7 shadow-soft">
        <BrandLogo showWordmark={false} className="mb-5 h-12 w-12 rounded-md bg-white" imageClassName="h-12 w-12 rounded-md object-contain" />

        <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-3">
          <ShieldAlert className="mt-0.5 shrink-0 text-amber-600" size={19} />
          <div className="text-sm leading-6 text-amber-900">
            <div className="font-semibold">Update your password to continue</div>
            Your current password does not meet the security requirements for this account. Set a
            stronger one to regain access.
          </div>
        </div>

        <h1 className="mt-5 text-2xl font-semibold text-ink">Choose a new password</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Use at least 8 characters with three of: lowercase, uppercase, number, symbol. Avoid common
          passwords and anything containing your name, email, or phone number.
        </p>

        {serverError ? (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div>
        ) : null}

        <form className="mt-5 space-y-4" onSubmit={form.handleSubmit(submit)}>
          <Field icon={<LockKeyhole size={17} />} label="Current password" error={form.formState.errors.currentPassword?.message}>
            <input {...form.register("currentPassword")} type="password" className="auth-input" placeholder="Your existing password" autoComplete="current-password" />
          </Field>
          <Field icon={<LockKeyhole size={17} />} label="New password" error={form.formState.errors.newPassword?.message}>
            <input {...form.register("newPassword")} type="password" className="auth-input" placeholder="Minimum 8 characters" autoComplete="new-password" />
          </Field>
          <Field icon={<LockKeyhole size={17} />} label="Confirm new password" error={form.formState.errors.confirmPassword?.message}>
            <input {...form.register("confirmPassword")} type="password" className="auth-input" placeholder="Re-enter new password" autoComplete="new-password" />
          </Field>
          <button
            type="submit"
            disabled={form.formState.isSubmitting}
            className="w-full rounded-md bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {form.formState.isSubmitting ? "Updating..." : "Update password and continue"}
          </button>
        </form>

        <div className="mt-5 text-center text-sm text-muted">
          Forgot your current password?{" "}
          <button
            type="button"
            className="font-semibold text-brand"
            onClick={() => {
              if (customer) {
                customerSession.clearCustomerSession();
                navigate("/customer/forgot-password", { replace: true });
                return;
              }
              auth.clearSession();
              navigate("/forgot-password", { replace: true });
            }}
          >
            Reset it with an OTP
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ icon, label, error, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <div className="flex items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/15">
        <span className="text-muted">{icon}</span>
        {children}
      </div>
      {error ? <span className="mt-1 block text-sm text-red-600">{error}</span> : null}
    </label>
  );
}
