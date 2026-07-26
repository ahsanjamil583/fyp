import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCustomerMe, loginCustomer, loginCustomerWithPhone, requestCustomerOtp } from "../../services/customerAuthApi.js";
import { AuthPanel } from "../auth/AuthPanel.jsx";

const schema = Joi.object({
  email: Joi.string().allow("").email({ tlds: false }).label("Email"),
  phone: Joi.string().allow("").min(7).label("Phone"),
  otpCode: Joi.string().allow("").min(4).label("OTP code"),
  password: Joi.string().allow("").label("Password"),
});

export function CustomerLogin() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setCustomerSession } = useCustomer();
  const [authVariant, setAuthVariant] = useState(searchParams.get("mode") === "password" ? "password" : "phoneOtp");
  const [serverError, setServerError] = useState("");
  const [serverErrorAction, setServerErrorAction] = useState(null);
  const [otpStatus, setOtpStatus] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: {
      email: searchParams.get("email") || "",
      phone: searchParams.get("phone") || "",
      otpCode: "",
      password: "",
    },
  });

  async function finishLogin(session) {
    setCustomerSession(session);
    const me = await getCustomerMe();
    setCustomerSession({ ...session, profile: me.profile });
    navigate("/customer/marketplace");
  }

  async function sendOtp() {
    setServerError("");
    setServerErrorAction(null);
    setOtpStatus("");
    const phone = form.getValues("phone");
    if (!phone) {
      setServerError("Enter your phone number first.");
      return;
    }
    setIsSendingOtp(true);
    try {
      const result = await requestCustomerOtp({ phone, purpose: "login", channel: "sms" });
      setOtpInfo(result);
      setOtpStatus(`OTP sent to ${result.maskedPhone || result.phone}.`);
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Could not send OTP."));
    } finally {
      setIsSendingOtp(false);
    }
  }

  async function submit(values) {
    setServerError("");
    setServerErrorAction(null);
    try {
      if (authVariant === "phoneOtp") {
        if (!otpInfo) {
          setServerError("Send OTP first, then enter the received/demo code.");
          return;
        }
        if (!values.phone || !values.otpCode) {
          setServerError("Enter phone number and OTP code.");
          return;
        }
        const session = await loginCustomerWithPhone({ phone: values.phone, code: values.otpCode });
        await finishLogin(session);
        return;
      }
      if (!values.email || !values.password) {
        setServerError("Enter email and password.");
        return;
      }
      const session = await loginCustomer({ email: values.email, password: values.password });
      await finishLogin(session);
    } catch (error) {
      const message = getApiErrorMessage(error, "Login failed.");
      if (error?.response?.status === 401 || /invalid credentials/i.test(message)) {
        setServerError("Invalid credentials. Try phone OTP login, or reset the password using your registered phone.");
        setServerErrorAction({ to: "/customer/login?mode=phoneOtp", label: "Use OTP login" });
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <AuthPanel
      title="Customer Login"
      subtitle="Sign in with phone OTP to continue shopping, chatting with business agents, and confirming orders quickly."
      mode="login"
      authVariant={authVariant}
      customer
      register={form.register}
      errors={form.formState.errors}
      isSubmitting={form.formState.isSubmitting}
      serverError={serverError}
      serverErrorActionTo={serverErrorAction?.to}
      serverErrorActionLabel={serverErrorAction?.label}
      onSubmit={form.handleSubmit(submit)}
      submitLabel={authVariant === "phoneOtp" ? "Sign in with OTP" : "Sign in"}
      switchLabel="Need a customer account?"
      switchTo="/customer/register"
      otpInfo={otpInfo}
      otpStatus={otpStatus}
      onSendOtp={sendOtp}
      isSendingOtp={isSendingOtp}
      onToggleAuthVariant={() => setAuthVariant(authVariant === "phoneOtp" ? "password" : "phoneOtp")}
      authVariantToggleLabel={authVariant === "phoneOtp" ? "Use email + password instead" : "Use phone OTP instead"}
      passwordResetTo="/customer/forgot-password"
    />
  );
}
