import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCustomerMe, registerCustomer } from "../../services/customerAuthApi.js";
import { AuthPanel } from "../auth/AuthPanel.jsx";

const schema = Joi.object({
  fullName: Joi.string().min(2).required().label("Full name"),
  email: Joi.string().email({ tlds: false }).required().label("Email"),
  password: Joi.string().min(8).required().label("Password"),
});

export function CustomerRegister() {
  const navigate = useNavigate();
  const { setCustomerSession } = useCustomer();
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { fullName: "", email: "", password: "" },
  });
  const [serverError, setServerError] = useState("");

  async function submit(values) {
    setServerError("");
    try {
      const payload = {
        fullName: values.fullName,
        email: values.email,
        password: values.password,
      };
      const session = await registerCustomer(payload);
      setCustomerSession(session);
      const me = await getCustomerMe();
      setCustomerSession({ ...session, profile: me.profile });
      navigate("/customer/marketplace");
    } catch (error) {
      const message = getApiErrorMessage(error, "Registration failed.");
      if (error?.response?.status === 409 || /already exists/i.test(message)) {
        setServerError("A customer account already exists with this email. Sign in, or reset the password if you forgot it.");
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <AuthPanel
      title="Create Customer Account"
      subtitle="Create your account with email and password to shop, chat with businesses, and track your orders."
      mode="register"
      authVariant="password"
      showPhone={false}
      customer
      register={form.register}
      errors={form.formState.errors}
      isSubmitting={form.formState.isSubmitting}
      serverError={serverError}
      onSubmit={form.handleSubmit(submit)}
      submitLabel="Create account"
      switchLabel="Already registered?"
      switchTo="/customer/login"
    />
  );
}
