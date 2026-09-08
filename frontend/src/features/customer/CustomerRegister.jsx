import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCustomerMe, registerCustomer, registerCustomerWithPhone, requestCustomerOtp } from "../../services/customerAuthApi.js";
import { AuthPanel } from "../auth/AuthPanel.jsx";

const schema = Joi.object({
  fullName: Joi.string().min(2).required().label("Full name"),
  phone: Joi.string().min(7).required().label("Phone"),
  email: Joi.string().allow("").email({ tlds: false }).label("Email"),
  password: Joi.string().min(8).required().label("Password"),
  otpCode: Joi.string().allow("").min(4).label("OTP code"),
});

function customerOtpLoginPath(phone) {
  const params = new URLSearchParams({ mode: "phoneOtp" });
  if (phone) {
    params.set("phone", phone);
  }
  return `/customer/login?${params.toString()}`;
}

export function CustomerRegister() {
  const navigate = useNavigate();
  const { setCustomerSession } = useCustomer();
  const [authVariant, setAuthVariant] = useState("phoneOtp");
  const [serverError, setServerError] = useState("");
  const [serverErrorAction, setServerErrorAction] = useState(null);
  const [otpStatus, setOtpStatus] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: { fullName: "", phone: "", email: "", password: "", otpCode: "" },
  });

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
      const result = await requestCustomerOtp({ phone, purpose: "register", channel: "sms" });
      setOtpInfo(result);
      setOtpStatus(`OTP sent to ${result.maskedPhone || result.phone}.`);
    } catch (error) {
      const message = getApiErrorMessage(error, "Could not send OTP.");
      if (error?.response?.status === 409 || /already exists/i.test(message)) {
        setServerError("This phone already has a customer account. Use phone OTP login instead, or reset the password if needed.");
        setServerErrorAction({ to: customerOtpLoginPath(phone), label: "Go to OTP login" });
      } else {
        setServerError(message);
      }
    } finally {
      setIsSendingOtp(false);
    }
  }

  async function submit(values) {
    setServerError("");
    setServerErrorAction(null);
    try {
      const payload = {
        fullName: values.fullName,
        phone: values.phone,
        password: values.password,
        ...(values.email ? { email: values.email } : {}),
      };
      if (authVariant === "phoneOtp" && !otpInfo) {
        setServerError("Send OTP first, then enter the received/demo code.");
        return;
      }
      const session = authVariant === "phoneOtp"
        ? await registerCustomerWithPhone({ ...payload, code: values.otpCode })
        : await registerCustomer(payload);
      setCustomerSession(session);
      const me = await getCustomerMe();
      setCustomerSession({ ...session, profile: me.profile });
      navigate("/customer/marketplace");
    } catch (error) {
      const message = getApiErrorMessage(error, "Registration failed.");
      if (error?.response?.status === 409 || /already exists/i.test(message)) {
        setServerError("A customer account already exists with this email or phone. Sign in with phone OTP, or reset the password if you forgot it.");
        setServerErrorAction({ to: customerOtpLoginPath(values.phone), label: "Go to OTP login" });
      } else {
        setServerError(message);
      }
    }
  }

  return (
    <AuthPanel
      title="Create Customer Account"
      subtitle="Verify your phone once, then use the customer chatbot to search products and place orders faster."
      mode="register"
      authVariant={authVariant}
      emailOptional
      customer
      register={form.register}
      errors={form.formState.errors}
      isSubmitting={form.formState.isSubmitting}
      serverError={serverError}
      serverErrorActionTo={serverErrorAction?.to}
      serverErrorActionLabel={serverErrorAction?.label}
      onSubmit={form.handleSubmit(submit)}
      submitLabel="Create account"
      switchLabel="Already registered?"
      switchTo="/customer/login"
      otpInfo={otpInfo}
      otpStatus={otpStatus}
      onSendOtp={sendOtp}
      isSendingOtp={isSendingOtp}
      onToggleAuthVariant={() => setAuthVariant(authVariant === "phoneOtp" ? "password" : "phoneOtp")}
      authVariantToggleLabel={authVariant === "phoneOtp" ? "Use email/password registration instead" : "Use phone OTP registration instead"}
    />
  );
}
