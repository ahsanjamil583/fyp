import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { loginBusiness } from "../../services/authApi.js";
import { getMyTenants } from "../../services/tenantApi.js";
import { AuthPanel } from "./AuthPanel.jsx";

const schema = Joi.object({
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  password: Joi.string().required().label("Password"),
});

export function BusinessLogin() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [serverError, setServerError] = useState("");
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  async function goAfterLogin(session) {
    setSession(session);
    if (session.user.mustResetPassword) {
      navigate("/update-password");
      return;
    }
    if (session.user.globalRole === "platform_admin") {
      navigate("/admin");
      return;
    }
    const tenants = await getMyTenants().catch(() => []);
    navigate(tenants.length ? "/dashboard" : "/dashboard/business");
  }

  async function submit(values) {
    setServerError("");
    try {
      const session = await loginBusiness({ email: values.email, password: values.password });
      await goAfterLogin(session);
    } catch (error) {
      const message = getApiErrorMessage(error, "Login failed.");
      if (error?.response?.status === 401 || /invalid credentials/i.test(message)) {
        setServerError("Invalid email or password. Use Forgot password if you need a reset code.");
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <AuthPanel
      title="Business Login"
      subtitle="Welcome back. Sign in to manage your storefront, orders, stock, payments, and AI assistant."
      mode="login"
      authVariant="password"
      register={form.register}
      errors={form.formState.errors}
      isSubmitting={form.formState.isSubmitting}
      serverError={serverError}
      onSubmit={form.handleSubmit(submit)}
      submitLabel="Sign in to workspace"
      switchLabel="Need a business account?"
      switchTo="/register"
      passwordResetTo="/forgot-password"
    />
  );
}
