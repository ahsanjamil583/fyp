# Phase 29 — Phone-First OTP Authentication and Onboarding Polish

## Goal

Phase 29 adds the phone-first account access flow required by the BizXusAI proposal. Business owners and customers can now request an OTP on their Pakistani mobile number, verify it, and use it for login, registration, and password reset. Email/password remains available as a fallback for existing accounts and admin users.

## Implemented backend features

### Business owner auth

New endpoints:

```text
POST /api/v1/auth/otp/request
POST /api/v1/auth/otp/verify
POST /api/v1/auth/login/phone
POST /api/v1/auth/register/phone
POST /api/v1/auth/password/phone/request
POST /api/v1/auth/password/phone/reset
POST /api/v1/auth/me/phone/request
POST /api/v1/auth/me/phone/verify
```

### Customer auth

New endpoints:

```text
POST /api/v1/customer/auth/otp/request
POST /api/v1/customer/auth/otp/verify
POST /api/v1/customer/auth/login/phone
POST /api/v1/customer/auth/register/phone
POST /api/v1/customer/auth/password/phone/request
POST /api/v1/customer/auth/password/phone/reset
POST /api/v1/customer/auth/me/phone/request
POST /api/v1/customer/auth/me/phone/verify
```

### OTP service

Added:

```text
backend/app/services/otp_service.py
backend/app/schemas/otp_schema.py
backend/tests/test_phase29_phone_otp.py
```

The OTP service includes:

- Pakistan mobile number normalization.
- OTP generation.
- OTP hashing using HMAC SHA-256.
- Expiry handling.
- Attempt limits.
- Immediate challenge lock on the final wrong attempt.
- Resend cooldown.
- API response metadata for code length, expiry seconds, and resend cooldown seconds.
- SMS/WhatsApp delivery seam.
- Demo-mode OTP return for FYP testing.
- Phone verification marking on successful OTP login/registration.

### Database additions

New collection:

```text
otp_challenges
```

Important fields:

```text
phone
accountType
purpose
channel
codeHash
attempts
maxAttempts
status
expiresAt
verifiedAt
usedAt
deliveryStatus
createdAt
updatedAt
```

Indexes added:

```text
phone + accountType + purpose + status
expiresAt TTL-style cleanup index
createdAt
```

The user email index was changed to sparse unique, so phone-first accounts can be created without forcing an email address.

## Implemented frontend features

### Business owner screens

Updated:

```text
frontend/src/features/auth/BusinessLogin.jsx
frontend/src/features/auth/BusinessRegister.jsx
frontend/src/features/auth/AuthPanel.jsx
frontend/src/services/authApi.js
```

Added:

```text
frontend/src/features/auth/PhonePasswordResetPage.jsx
```

Business owners can now:

- Register with phone OTP.
- Login with phone OTP.
- Switch back to email/password login.
- Reset password using phone OTP.
- Use email as optional during phone-first registration.
- See OTP expiry, code length, resend cooldown, and demo code guidance after requesting OTP.

### Customer screens

Updated:

```text
frontend/src/features/customer/CustomerLogin.jsx
frontend/src/features/customer/CustomerRegister.jsx
frontend/src/services/customerAuthApi.js
```

Customers can now:

- Register with phone OTP.
- Login with phone OTP.
- Switch back to email/password login.
- Reset password using phone OTP.
- Continue into marketplace/customer chatbot after OTP login.
- See OTP expiry, code length, resend cooldown, and demo code guidance after requesting OTP.

### New routes

```text
/forgot-password
/customer/forgot-password
```

## Environment variables

Added to `.env.example`:

```text
OTP_CODE_LENGTH=6
OTP_EXPIRE_MINUTES=10
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=30
OTP_DEMO_CODE=123456
OTP_RETURN_CODE_IN_RESPONSE=true
```

For development/FYP demo, the backend returns the OTP code in the response. In production, keep `OTP_RETURN_CODE_IN_RESPONSE=false`.

## Demo testing flow

### Business owner registration

1. Open `/register`.
2. Enter full name and phone number.
3. Click **Send OTP**.
4. Use demo OTP `123456` if demo mode is enabled.
5. Create account.
6. Continue to `/dashboard/business`.

### Business owner login

1. Open `/login`.
2. Enter phone number.
3. Click **Send OTP**.
4. Enter OTP.
5. Login.

### Customer registration/login

1. Open `/customer/register` or `/customer/login`.
2. Use phone OTP flow.
3. After login, customer is redirected to marketplace.
4. Customer can open a business chatbot and say: `black shoes order kar do`.

## Why this phase matters

The proposal says business owners should start with their phone number and should not need technical setup. This phase makes authentication and onboarding closer to that proposal by making phone the main identity channel, while keeping email/password as a fallback.

## Checks completed

```text
Backend Python compile check: passed
Backend unittest suite: 48 tests passed
Frontend npm install: passed
Frontend production build: passed
```
