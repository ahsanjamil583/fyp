from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from html import escape

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    pass


def should_use_email_demo_delivery() -> bool:
    return bool(settings.otp_demo_mode)


def _sender() -> tuple[str, str]:
    from_email = (settings.smtp_from_email or settings.smtp_username or "").strip()
    from_name = (settings.smtp_from_name or "BizXusAI").strip()
    if not from_email:
        raise EmailSendError("SMTP_FROM_EMAIL or SMTP_USERNAME is required.")
    return from_email, from_name


def build_otp_email_body(code: str) -> str:
    return (
        "Hello,\n\n"
        "Your BizXusAI verification code is:\n\n"
        f"{code}\n\n"
        f"This code will expire in {settings.otp_expire_minutes} minutes.\n\n"
        "If you did not request this code, please ignore this email.\n\n"
        "Regards,\n"
        "BizXusAI Team"
    )


def build_otp_email_html(code: str) -> str:
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#eef3f9;font-family:Arial,Helvetica,sans-serif;color:#172033;">
    <div style="display:none;max-height:0;overflow:hidden;color:#eef3f9;">Your BizXusAI verification code is {code}. It expires in {settings.otp_expire_minutes} minutes.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef3f9;padding:36px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #d7e2ef;border-radius:22px;overflow:hidden;box-shadow:0 18px 45px rgba(15,23,42,0.08);">
            <tr>
              <td style="padding:28px 32px;background:#172033;color:#ffffff;">
                <div style="font-size:12px;font-weight:800;letter-spacing:0.22em;text-transform:uppercase;color:#93c5fd;">BizXusAI Secure Access</div>
                <h1 style="margin:12px 0 6px;font-size:28px;line-height:1.2;font-weight:800;">Verify your email</h1>
                <p style="margin:0;color:#dbeafe;font-size:15px;line-height:1.6;">Use this one-time code to continue creating your business workspace.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="margin:0 0 12px;color:#64748b;font-size:15px;line-height:1.7;">Your verification code is:</p>
                <div style="margin:14px 0 24px;padding:22px 18px;border-radius:18px;background:#eef4ff;border:1px solid #dbeafe;text-align:center;">
                  <div style="font-size:40px;line-height:1;font-weight:900;letter-spacing:0.34em;color:#172033;">{code}</div>
                </div>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 22px;">
                  <tr>
                    <td style="padding:14px 16px;border-radius:14px;background:#f8fafc;border:1px solid #e2e8f0;color:#475569;font-size:14px;line-height:1.6;">
                      This code expires in <strong style="color:#172033;">{settings.otp_expire_minutes} minutes</strong>. For your security, do not share it with anyone.
                    </td>
                  </tr>
                </table>
                <p style="margin:0;color:#64748b;font-size:14px;line-height:1.7;">If you did not request this code, you can safely ignore this email. Your account will not be changed.</p>
                <p style="margin:26px 0 0;color:#172033;font-size:14px;line-height:1.7;">Regards,<br /><strong>BizXusAI Team</strong></p>
              </td>
            </tr>
          </table>
          <p style="max-width:620px;margin:18px auto 0;color:#94a3b8;font-size:12px;line-height:1.6;text-align:center;">BizXusAI helps businesses manage websites, customers, orders, payments, and AI automation from one workspace.</p>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_email(*, to_email: str, subject: str, body: str) -> dict:
    provider = str(settings.email_provider or "smtp").strip().lower()
    if provider != "smtp":
        raise EmailSendError(f"Unsupported email provider: {provider}")

    smtp_username = str(settings.smtp_username or "").strip()
    smtp_password = "".join(str(settings.smtp_password or "").split())
    if not settings.smtp_host or not smtp_username or not smtp_password:
        raise EmailSendError("SMTP is not configured. Please check EMAIL_PROVIDER and SMTP settings.")

    from_email, from_name = _sender()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        logger.exception(
            "SMTP email send failed provider=%s host=%s from=%s to=%s error=%s",
            provider,
            settings.smtp_host,
            from_email,
            to_email,
            type(exc).__name__,
        )
        raise EmailSendError(str(exc)) from exc

    return {"provider": provider, "fromEmail": from_email, "toEmail": to_email, "subject": subject}


def send_otp_email(*, to_email: str, code: str) -> dict:
    if should_use_email_demo_delivery():
        logger.warning("Email OTP demo delivery active for %s. OTP is %s and no real email was sent.", to_email, code)
        return {"provider": "demo", "toEmail": to_email, "subject": "BizXusAI Verification Code"}

    try:
        body = build_otp_email_body(code)
        html_body = build_otp_email_html(code)
        provider = str(settings.email_provider or "smtp").strip().lower()
        if provider != "smtp":
            raise EmailSendError(f"Unsupported email provider: {provider}")
        smtp_username = str(settings.smtp_username or "").strip()
        smtp_password = "".join(str(settings.smtp_password or "").split())
        if not settings.smtp_host or not smtp_username or not smtp_password:
            raise EmailSendError("SMTP is not configured. Please check EMAIL_PROVIDER and SMTP settings.")
        from_email, from_name = _sender()
        message = EmailMessage()
        message["Subject"] = "BizXusAI Verification Code"
        message["From"] = f"{from_name} <{from_email}>"
        message["To"] = to_email
        message.set_content(body)
        message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        return {"provider": provider, "fromEmail": from_email, "toEmail": to_email, "subject": "BizXusAI Verification Code"}
    except EmailSendError as exc:
        logger.error(
            "Email OTP delivery failed provider=%s host=%s from=%s to=%s error=%s",
            settings.email_provider,
            settings.smtp_host,
            settings.smtp_from_email or settings.smtp_username,
            to_email,
            exc,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email OTP delivery failed: {exc}") from exc
    except Exception as exc:
        logger.exception(
            "SMTP email send failed provider=%s host=%s from=%s to=%s error=%s",
            settings.email_provider,
            settings.smtp_host,
            settings.smtp_from_email or settings.smtp_username,
            to_email,
            type(exc).__name__,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email OTP delivery failed: {exc}") from exc


def build_payment_otp_email_body(
    code: str,
    *,
    amount: float,
    currency: str,
    business_name: str,
    order_number: str,
    provider_label: str,
) -> str:
    return (
        "Hello,\n\n"
        f"Use this code to confirm your {provider_label} payment of {currency} {amount:,.2f} "
        f"to {business_name} for order {order_number}:\n\n"
        f"{code}\n\n"
        f"The code expires in {settings.payment_otp_expire_minutes} minutes.\n\n"
        "If you did not start this payment, ignore this email. Nothing will be charged.\n\n"
        "Note: this is a simulated payment used for demonstration. No real money is transferred.\n\n"
        "Regards,\n"
        "BizXusAI Team"
    )


def build_payment_otp_email_html(
    code: str,
    *,
    amount: float,
    currency: str,
    business_name: str,
    order_number: str,
    provider_label: str,
) -> str:
    safe_business = escape(str(business_name or "the business"))
    safe_order = escape(str(order_number or ""))
    safe_provider = escape(str(provider_label or "wallet"))
    safe_currency = escape(str(currency or "PKR"))
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#eef3f9;font-family:Arial,Helvetica,sans-serif;color:#172033;">
    <div style="display:none;max-height:0;overflow:hidden;color:#eef3f9;">Your {safe_provider} payment code is {code}. It expires in {settings.payment_otp_expire_minutes} minutes.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef3f9;padding:36px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #d7e2ef;border-radius:22px;overflow:hidden;box-shadow:0 18px 45px rgba(15,23,42,0.08);">
            <tr>
              <td style="padding:28px 32px;background:#172033;color:#ffffff;">
                <div style="font-size:12px;font-weight:800;letter-spacing:0.22em;text-transform:uppercase;color:#93c5fd;">BizXusAI Payment</div>
                <h1 style="margin:12px 0 6px;font-size:28px;line-height:1.2;font-weight:800;">Confirm your payment</h1>
                <p style="margin:0;color:#dbeafe;font-size:15px;line-height:1.6;">{safe_provider} payment to {safe_business}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 22px;">
                  <tr><td style="padding:6px 0;color:#64748b;font-size:14px;">Order</td><td align="right" style="padding:6px 0;font-weight:700;font-size:14px;">{safe_order}</td></tr>
                  <tr><td style="padding:6px 0;color:#64748b;font-size:14px;">Amount</td><td align="right" style="padding:6px 0;font-weight:800;font-size:18px;">{safe_currency} {amount:,.2f}</td></tr>
                </table>
                <p style="margin:0 0 12px;color:#64748b;font-size:15px;line-height:1.7;">Enter this code to complete the payment:</p>
                <div style="margin:14px 0 24px;padding:22px 18px;border-radius:18px;background:#eef4ff;border:1px solid #dbeafe;text-align:center;">
                  <div style="font-size:40px;line-height:1;font-weight:900;letter-spacing:0.34em;color:#172033;">{code}</div>
                </div>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 18px;">
                  <tr>
                    <td style="padding:14px 16px;border-radius:14px;background:#f8fafc;border:1px solid #e2e8f0;color:#475569;font-size:14px;line-height:1.6;">
                      This code expires in <strong style="color:#172033;">{settings.payment_otp_expire_minutes} minutes</strong>. Do not share it with anyone.
                    </td>
                  </tr>
                </table>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 22px;">
                  <tr>
                    <td style="padding:14px 16px;border-radius:14px;background:#fef3c7;border:1px solid #fcd34d;color:#78350f;font-size:13px;line-height:1.6;">
                      <strong>Simulated payment.</strong> This is a demonstration of the payment flow. No real money is transferred.
                    </td>
                  </tr>
                </table>
                <p style="margin:0;color:#64748b;font-size:14px;line-height:1.7;">If you did not start this payment, you can safely ignore this email. Nothing will be charged.</p>
                <p style="margin:26px 0 0;color:#172033;font-size:14px;line-height:1.7;">Regards,<br /><strong>BizXusAI Team</strong></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_payment_otp_email(
    *,
    to_email: str,
    code: str,
    amount: float,
    currency: str,
    business_name: str,
    order_number: str,
    provider_label: str,
) -> dict:
    """Send a payment confirmation code.

    Unlike :func:`send_otp_email`, this has no demo short-circuit. A payment code that is
    only written to the server log cannot be typed in by the customer sitting at the
    checkout, so OTP_DEMO_MODE is deliberately not consulted here: email is the delivery
    channel, always.
    """
    subject = f"Your {provider_label} payment code for {order_number}".strip()
    body = build_payment_otp_email_body(
        code,
        amount=amount,
        currency=currency,
        business_name=business_name,
        order_number=order_number,
        provider_label=provider_label,
    )
    html_body = build_payment_otp_email_html(
        code,
        amount=amount,
        currency=currency,
        business_name=business_name,
        order_number=order_number,
        provider_label=provider_label,
    )

    provider = str(settings.email_provider or "smtp").strip().lower()
    if provider != "smtp":
        raise EmailSendError(f"Unsupported email provider: {provider}")
    smtp_username = str(settings.smtp_username or "").strip()
    smtp_password = "".join(str(settings.smtp_password or "").split())
    if not settings.smtp_host or not smtp_username or not smtp_password:
        raise EmailSendError("SMTP is not configured. Please check EMAIL_PROVIDER and SMTP settings.")

    from_email, from_name = _sender()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        # The code must never reach a log line, even on failure.
        logger.error(
            "Payment OTP email failed provider=%s host=%s to=%s error=%s",
            provider,
            settings.smtp_host,
            to_email,
            type(exc).__name__,
        )
        raise EmailSendError(str(exc)) from exc

    return {"provider": provider, "fromEmail": from_email, "toEmail": to_email, "subject": subject}
