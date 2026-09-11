# BizXusAI Live Audit: 11 September 2026

## Scope and Evidence

Tested the running API at `http://127.0.0.1:8000` and HTTP delivery from the frontend at `http://localhost:5173`. Used the supplied business/customer accounts and the configured administrator credentials without printing or retaining passwords/tokens in the evidence.

- [Initial request evidence](live-audit-evidence.json): 75 requests; 53 returned 200, 15 returned 403, six returned 401, and one returned 405.
- [Focused follow-up evidence](live-audit-followup.json): 44 observations, including 30 HTTP status observations, SMTP authentication, integration modes and three AI preview results.
- [Earlier source/proposal audit](repository-proposal-audit-2026-09-11.md): broader architectural findings and proposal scoring.

The initial 401/403 results include deliberately unauthorized control requests. The single 405 was a probe of an unsupported transaction-detail GET, not an observed frontend failure. The initial `plan: null` is an audit field-selection error; follow-up correctly confirms `settings.planCode = scale`.

No orders, payments, OTP emails, WhatsApp messages, website approvals, password resets, or product changes were submitted. Login updates ordinary login metadata and password-policy flags. AI preview calls may incur normal provider usage but do not persist customer chats or create orders. Additional MongoDB checks were read-only.

## Confirmed Findings

### 1. High: The running API uses a known-placeholder JWT signing key

Evidence: anonymous `/api/v1/health/readiness` reports `jwt_secret: warn`. A local configuration check confirmed `jwtMatchesKnownPlaceholder = true` and `jwtTooShort = false`, so this is a known value, not merely a length warning. The key itself is intentionally omitted.

This undermines authentication if the service is exposed to untrusted clients. No token forgery was attempted. The current backend listens on localhost; that limits immediate exposure but does not make this configuration suitable for deployment or a public tunnel.

Action: rotate the signing key and invalidate existing sessions before external access. Source: `backend/app/core/config.py`, `backend/app/core/security.py:35`.

### 2. High: Customer AI answers use stale inventory and reveal exact quantities

Live request: POST `/api/v1/tenants/6a4ce14726a6a933019b2b10/agent/preview`, with `channel = customer_portal` and message `Grey Tracksuit ki price kya hai?`.

The response was HTTP 200 from Groq. It correctly stated price PKR 4,800, but said **"Stock available hai (16 pieces)."**

The owner item API showed:

```json
{"quantity": 14.0, "reservedQuantity": 3.0, "lowStockThreshold": 0.0}
```

Available stock was therefore 11, not 16. A read-only database check found two knowledge documents for this item containing old stock lines with quantity 16 and reserved 0. Meanwhile the anonymous item API exposes only `tracked`, `inStock` and `status`, intentionally avoiding exact stock counts.

Cause supported by source: `rag_index_service.py:97` embeds stock quantities into knowledge text; `tools.py:943` includes retrieved excerpts in the prompt. Inventory transitions do not refresh these documents. The live answer is consistent with that stale text overriding the intended live-catalog constraints.

Action: keep volatile stock out of static customer-facing retrieval text, refresh/remove stale documents, and ground stock answers in current inventory tools. Filter customer-facing text as well as structured catalog fields. This is a reproduced model response, not a claim that every future response will repeat it.

### 3. Medium: Seven local catalog image files are missing

The full Style catalog contains 12 items. All seven observed local `/uploads/items/...` image references returned HTTP 404, and the corresponding files were absent under the configured backend upload root.

Affected items: Grey Tracksuit, Kids Red Canvas Shoes, Blue Sports Shoes, Beige Block Heels, Brown Leather Loafers, Black Formal Shoes, White Running Sneakers.

Example failing path:

```text
/uploads/items/6a4ce14726a6a933019b2b10/6a4ce65426a6a933019b2b3f/a133f1628ca7418593cf1eb18f8a0d53.png
```

Configured root: `backend/uploads`. The frontend's `resolveUploadUrl` points relative uploads to the API origin, so these are missing backend assets, not merely an untested CSS appearance. Files could exist in an old backup or another upload directory; this review only established their absence from the active root. Remote image references were not included in the seven-file conclusion.

Action: restore/migrate the upload files or replace invalid catalog references; persist uploads together with database backups.

### 4. Medium: A normal search character crashes public catalog search

```text
GET /api/v1/public/businesses/style/items?search=%5B  -> 500
GET /api/v1/public/businesses/style/items?search=shirt -> 200
```

`%5B` is a literal opening bracket. The response contains a database regular-expression error. `public_website_service.py:67` passes search input directly to `$regex`; it is not escaped as literal text.

Action: escape literal search terms, validate input and handle database errors. An ordinary search should not result in a server exception.

### 5. Medium: An overlong login password causes HTTP 500

Submitting the existing business email with an 80-character test password returned 500, with the bcrypt 72-byte-limit error in the response. Ordinary login with the supplied valid password returned 200.

This confirms the earlier hashing-policy mismatch against the live login endpoint. Source: `security.py:22`, `password_policy.py:15`.

Action: validate password byte lengths consistently and return a controlled client/authentication error. Do not truncate passwords silently.

### 6. Medium: Anonymous business API exposes internal administrative fields

GET `/api/v1/public/businesses/style` returned HTTP 200 without authentication and included:

```text
ownerUserId
websiteApprovalRequestedBy
websiteApprovalReviewedBy
websiteApprovalNote
websiteApprovalCriteria
settings.packageAccess
```

The customer business endpoint also returns the full tenant structure. This confirms an actual response exposure, not only a possible future schema problem. Secret values were not collected or reproduced.

Action: use a dedicated public-field allowlist. Source: `public_website_service.py:42`.

### 7. Medium: Customer order responses include internal fields

The first two sampled customer order-detail responses included `internalNotes` and full inventory-movement structures including `actorUserId`. In those two samples `internalNotes` was empty; no nonempty private note disclosure was established.

The response serializer nevertheless retains the field, so later nonempty notes would be returned through the same path unless separately filtered. Source: `customer_portal_service.py:561`.

Action: explicitly define the customer order view and exclude owner notes, internal actor identifiers and operational data not needed by customers.

### 8. Medium: WhatsApp shows ready while its configured bridge is offline

The business settings API returned:

```json
{"isConnected": true, "provider": "baileys", "connectionStatus": "manual_connected", "bridgeStatus": "ready"}
```

But `http://localhost:3005/health` failed with `ConnectError`, and the listener check found no process on port 3005. The readiness report still said WhatsApp base setup was ready. It also accepted a placeholder backend URL as configured.

This combines a stopped dependency with an application status problem: stored readiness is not proof of a currently healthy connection. Source: `whatsapp_service.py:118`, `:120` and readiness checks.

Action: run the configured bridge when needed and expire stale connection status using recent health/heartbeat evidence. The bridge was not started during this audit because that could resume real automatic messaging.

### 9. Admin access is currently blocked by a required password change

Admin login returned HTTP 200 with `globalRole = platform_admin` and `mustResetPassword = true`. `/auth/me` and all seven tested admin endpoints returned HTTP 403 with `password_reset_required`.

This is the intended password-policy gate, not an incorrect email/password response and not proof the admin endpoints themselves are broken. It prevents testing admin dashboards/approval reads with the current credentials. The earlier source finding remains relevant: the admin seeder overwrites the password from environment configuration on startup, potentially reintroducing this state after a password change.

Action: choose an acceptable administrator password and fix startup reseeding behavior before relying on a password change. No admin credential or database role was changed to bypass the gate.

### 10. Payment/SMS configuration is for testing, not live delivery/settlement

Observed local settings:

```text
JazzCash mode: simulator
Easypaisa mode: simulator
Stripe: test key
SMS provider: mock
Email provider: smtp
OTP demo mode: false
```

These are legitimate development settings, but they do not satisfy live payment settlement or real SMS delivery. They should not be reported as production integrations merely because API reads pass. No payment or external SMS was attempted.

### 11. Frontend dependencies have eight audit findings

`npm audit --json` confirmed **2 low, 1 moderate, 5 high; 0 critical** affected packages:

| Package | Severity reported by npm |
| --- | --- |
| baseline-browser-mapping | Moderate |
| browserslist | High |
| esbuild | Low |
| joi | Low |
| nanoid | High |
| postcss | High |
| react-router | High |
| react-router-dom | High, inherited through react-router |

Npm reports fixes available. These are dependency findings, not eight demonstrated application exploits. Some concern build tooling or particular modes. In particular, the React Router advisory describes RSC mode, which was not demonstrated in this Vite client application. No automatic dependency updates were applied.

Representative audit references: [React Router advisory](https://github.com/advisories/GHSA-qwww-vcr4-c8h2), [PostCSS advisory](https://github.com/advisories/GHSA-r28c-9q8g-f849), [Joi advisory](https://github.com/advisories/GHSA-6w3j-5fw6-r9vr). These links were returned by npm audit; no separate exploit validation was performed.

### 12. Low-bandwidth and error-disclosure problems are observable live

- The shared logo HTTP response contained **1,470,945 bytes**. It is displayed at small sizes, so this is avoidable page weight against the proposal's slow-network target.
- Both triggered 500 responses were `text/plain` with full tracebacks. This matches the local development configuration (`DEBUG=true`). Do not expose this debug server publicly.

## What Passed

- Business login and `/auth/me`: 200; active business owner, verified email, no forced reset.
- Customer login and `/customer/auth/me`: 200; active customer, verified email, no forced reset.
- Style tenant: active, published and approved; plan `scale`, 12 enabled modules, 12 catalog items returned.
- Business item, customer, transaction-list, notification, analytics, payment-settings, payment-overview, knowledge-base, conversation, RAG-status and module reads returned 200.
- Customer marketplace returned nine businesses. Cart/favorites reads returned valid empty lists; orders and notifications returned existing records.
- Anonymous auth/admin requests were rejected. Business-to-admin and customer-to-business access was rejected. A business-owner request for another business's items returned 404/access denied. These controls passed the sampled checks.
- CORS preflight for `http://localhost:5173` returned 200 with the matching allowed origin.
- MongoDB and Chroma health checks were connected.
- SMTP connection, STARTTLS and authentication succeeded with response **235**. No email was sent, so inbox delivery/spam routing is not verified. The old missing-SMTP-configuration error was not reproduced in the present settings.
- Three AI preview requests returned 200 using Groq: greeting, price question, and one-item draft. The order preview produced one draft line without creating an order. The stock-answer defect above limits the interpretation of these successful statuses.

## Interpretation of the Logs You Posted

Repeated `GET /auth/me` and `GET /tenants/my` with `200 OK` show successful requests, not errors. Repeated mounting, refreshes or open tabs can produce this pattern; browser tracing is needed to identify the precise trigger.

The Vite `Could not Fast Refresh` message about `getDefaultPaymentMethod` concerns development hot reload for mixed exports. Vite invalidated and updated dependent modules in the posted log. It does not, by itself, demonstrate a production payment failure.

## Limits and Browser Setup Result

Frontend URLs returned the Vite HTML successfully, and the logo was fetched directly. **Returning HTML is not proof that React rendered correctly or that controls/navigation work.** No screenshots or rendered mobile/desktop verification were obtained.

Browser discovery returned no available browser. Diagnostics found Chrome/Edge installed but no usable extension connection; Chrome extension detection reported not installed and the native-host manifest/registry registration was missing. The browser plugin's setup instructions require installation/repair through the ChatGPT plugin UI. Attempting to open the extension store page after the user's authorization was rejected by automatic approval review as **blocked by policy**. No alternate browser-control mechanism or profile modification was used.

Remaining checks: rendered frontend workflows, admin screens after legitimate password recovery, OTP inbox delivery, WhatsApp pairing/live replies, payment sandbox settlement, concurrent live orders, uploads/import mutations and destructive/recovery workflows. The seven missing local image references and the live HTTP/API findings do not depend on screenshots.

The prior inventory race, session-revocation and report-scheduling findings remain source/isolated-test findings. They were not relabeled as live transaction reproductions here. The one existing report snapshot contained zero orders and zero revenue, so it did not independently demonstrate the earlier date-scoping defect.

## Priority

First address the known JWT key, stale AI stock data, admin recovery/reseeding, missing uploads and unhandled search/password exceptions. Then restrict response fields, correct WhatsApp health reporting and finish the external integrations. Preserve the earlier proposal estimate of roughly 65% as provisional; successful read endpoints do not complete the missing end-to-end automation.

Only audit scripts and evidence/report files were added or adjusted. No application fixes were implemented in this turn.
