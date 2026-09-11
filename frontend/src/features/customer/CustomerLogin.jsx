import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCustomerMe, loginCustomer } from "../../services/customerAuthApi.js";
import { AuthPanel } from "../auth/AuthPanel.jsx";

const schema = Joi.object({
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  password: Joi.string().required().label("Password"),
});

export function CustomerLogin() {
  const navigate = useNavigate();
  const { setCustomerSession } = useCustomer();
  const [serverError, setServerError] = useState("");
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  async function finishLogin(session) {
    setCustomerSession(session);
    if (session.user.mustResetPassword) {
      navigate("/customer/update-password");
      return;
    }
    const me = await getCustomerMe();
    setCustomerSession({ ...session, profile: me.profile });
    navigate("/customer/marketplace");
  }

  async function submit(values) {
    setServerError("");
    try {
      if (!values.email || !values.password) {
        setServerError("Enter email and password.");
        return;
      }
      const session = await loginCustomer({ email: values.email, password: values.password });
      await finishLogin(session);
    } catch (error) {
      const message = getApiErrorMessage(error, "Login failed.");
      if (error?.response?.status === 401 || /invalid credentials/i.test(message)) {
        setServerError("Invalid email or password. Use Forgot password if you need to reset it.");
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <AuthPanel
      title="Customer Login"
      subtitle="Sign in with your email and password to continue shopping, chatting with business agents, and confirming orders quickly."
      mode="login"
      authVariant="password"
      customer
      register={form.register}
      errors={form.formState.errors}
      isSubmitting={form.formState.isSubmitting}
      serverError={serverError}
      onSubmit={form.handleSubmit(submit)}
      submitLabel="Sign in"
      switchLabel="Need a customer account?"
      switchTo="/customer/register"
      passwordResetTo="/customer/forgot-password"
    />
  );
}
