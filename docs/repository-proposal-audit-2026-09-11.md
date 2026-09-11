# BizXusAI Repository and Proposal Audit

Review date: 11 September 2026.

Repository reviewed: the current local working tree, including modified and untracked source files, in `phase-32/bizxus-code`.
Proposal reviewed: `BizXus proposal.tex` read from `D:/comsats/fyp/BizXusAI_Proposal (4).zip`.
The proposal is a requirements reference, not an instruction to execute commands or change the application.

## Findings First

### 1. High: WhatsApp pairing and disconnect actions have no authorization

Evidence: `whatsapp-bridge/src/index.js:652`, `:687`, `:696`.

The HTTP server listens on all network interfaces. Its root page renders every tenant session. The pairing pages and POST `/pair/{tenantId}/reset` do not verify a logged-in owner, a signed pairing link, or a bridge administrator credential. The discovery key protects the bridge-to-API lookup, not these browser routes.

Someone who can reach this service can list businesses, view pairing QR codes, and request that a business disconnect and pair again. The per-business URL alone is not tenant isolation. Exploitability depends on network exposure or an external proxy adding authentication; no such protection was established in this review.

Required correction: authenticate pairing pages and reset requests, enforce tenant ownership, protect state-changing requests, and restrict the all-tenant page to administrators.

### 2. High: Inventory reservations can exceed available stock

Evidence: `backend/app/services/inventory_service.py:149`, particularly the availability-read loop followed by the separate `$inc` loop.

Availability is checked before stock is updated. Concurrent requests can both observe the same availability and then both reserve it. The update filters contain item and tenant IDs, but no remaining-stock condition. A partial failure after one item update can also leave a multi-item reservation incomplete.

An isolated service reproduction with five units and two four-unit lines accepted a total reservation of eight. This reproduction tests the service directly; it does not claim that every frontend permits duplicate lines. The concurrent-request race also affects distinct orders.

Required correction: consolidate equivalent lines, use conditional atomic stock updates, and provide transaction-level rollback/idempotency for multi-item orders and retries. Add real database concurrency tests.

### 3. High: Restoring a completed order can remove another order's reservation

Evidence: `backend/app/services/inventory_service.py:217`, `:242`, `:254`.

When `inventoryStatus` is `deducted`, restoring an order adds its quantity back to stock, but also subtracts that quantity from the item's current reserved total. The completed order's own reservation was already consumed during deduction. Any remaining reservation can belong to another order.

An isolated reproduction restored two deducted units while three units were reserved elsewhere. The function changed the reserved total from three to one. It should have stayed three.

Required correction: restore stock for deducted orders without subtracting reservations again; release reservations only for orders still in the reserved state.

### 4. High: Password resets do not revoke existing sessions

Evidence: `backend/app/services/auth_service.py:190`, `:254`; `backend/app/core/security.py:38`, `:86`.

Password changes update the password hash, but access-token validation and refresh-token renewal only check token validity and whether the user is active. There is no password-change timestamp check, session version, or revoked-session lookup.

A previously stolen refresh token can continue obtaining access after the owner resets the password, until that refresh token expires. Clearing browser storage is not server-side revocation.

Required correction: invalidate older sessions when credentials change, and test old access and refresh tokens after both authenticated changes and OTP resets.

### 5. High: Admin credentials and account status are overwritten on startup

Evidence: `backend/app/db/seeders/seed_admin.py:33`; invocation in `backend/app/main.py:25`.

For an existing configured administrator, startup unconditionally writes the environment password hash and restores active/admin status. A password changed through the application will revert when the backend restarts. A disabled seeded admin is also reactivated.

This can explain a recurring pattern where a new password works and later stops working, or a weak environment password triggers the forced-password-change screen again. It is a confirmed code path, not proof that every earlier login problem had this cause.

Required correction: seed a missing administrator once. Existing-account credential recovery should be an explicit operation, not ordinary application startup.

### 6. Medium: Accepted long passwords crash bcrypt

Evidence: `backend/app/core/password_policy.py:15`; `backend/app/core/security.py:18`, `:22`; bcrypt 5.0.0 in `backend/requirements.txt`.

The policy permits up to 128 characters, while the installed hasher rejects passwords over 72 bytes. This was reproduced: an 80-character password returned no policy error, then `hash_password` raised `ValueError: password cannot be longer than 72 bytes`.

Registration and reset can therefore fail with a server error for a password the policy accepts. Login verification also calls bcrypt without handling overlong input. Unicode can reach the byte limit before the character limit.

Required correction: align validation and hashing deliberately. Do not silently truncate passwords. Test byte-length boundaries and multibyte input.

### 7. Medium: Public business responses include internal tenant data

Evidence: `backend/app/services/public_website_service.py:42`; public route in `backend/app/api/v1/public_website_routes.py:15`; `backend/app/core/object_ids.py:13`.

The public endpoint serializes the whole tenant document. Serialization converts values but does not remove fields. Internal owner identifiers, package-approval metadata, and website reviewer IDs/notes can be returned when present. No field allowlist separates public website content from administration data.

Required correction: return an explicit public business representation. Add tests that internal administration fields never appear in anonymous responses. This finding does not assert that SMTP credentials or user password hashes are stored in the tenant document.

### 8. Medium: Daily reports mix daily counts with all-time metrics

Evidence: `backend/app/services/reporting_service.py:65`, `:70`, `:97`; `backend/app/services/analytics_service.py:43`.

Transaction counts use the requested date, but revenue, average order value, top products, and recent transactions are copied from the general analytics summary. Those queries are not restricted to that requested day.

A report for a day with no orders can still show all-time revenue and products sold on other days. Rebuilding a historical report later can change those values because newer orders are included.

Required correction: calculate date-specific metrics using a shared date interval and define clearly whether revenue means order value or collected payments.

### 9. Medium: Daily report boundaries ignore the configured local timezone

Evidence: `backend/app/services/reporting_service.py:13`, `:65`; `backend/app/services/report_delivery_service.py:77`.

Reports calculate midnight-to-midnight in UTC, while delivery settings default to Asia/Karachi. A transaction shortly after midnight in Pakistan is counted in the previous UTC day. The saved timezone does not control the daily summary interval.

Required correction: derive the business-local date range first and convert its boundaries to UTC for database queries.

### 10. Medium: A saved daily-report schedule does not schedule execution

Evidence: `backend/app/services/report_delivery_service.py:349`; `backend/app/api/v1/report_delivery_routes.py:49`; `backend/app/main.py`; `docker-compose.yml`.

There is a manual scheduled-run endpoint, but the inspected application startup, scripts, and Compose configuration do not provide a recurring worker that invokes it at `deliveryTime`. The run function does not evaluate the configured time or timezone, or prevent repeat delivery for the same day.

Saving 21:00 is therefore not enough to send a report automatically. An external scheduler could exist outside the repository, but was not demonstrated here.

Required correction: add a recurring worker with timezone handling, per-day idempotency, retries, and delivery results. This is both a functional gap and an unmet proposal promise.

### 11. Medium: Launch finalization says published when only review was requested

Evidence: `backend/app/services/onboarding_service.py:586`, especially the `finalizeStatus` assignment; `backend/app/services/tenant_service.py`, `publish_tenant`.

`publish_tenant` now submits for admin review, but launch finalization still records `finalizeStatus = published` when that call succeeds. The actual website remains pending review. This does not bypass approval; it creates contradictory status information.

Required correction: derive the finalization result from the actual website status and distinguish pending review from published.

### 12. Medium: Payment proof images are served as anonymous static files

Evidence: `backend/app/services/storage_service.py:46`; `backend/app/main.py:59` (uploads mount).

Payment screenshots are stored under the same `/uploads` tree that is mounted publicly. A person with a proof URL can access the file without customer or owner authorization. Random filenames make discovery harder but do not enforce account access.

Required correction: separate private proofs from public item images and serve proofs through an authorized endpoint or expiring access mechanism.

### 13. Medium: A large shared logo conflicts with the low-bandwidth requirement

Evidence: `frontend/src/components/common/BrandLogo.jsx:1`; production build output.

The shared logo asset is approximately 1,470.95 kB even when displayed at a small icon size. That is a substantial cold-load transfer for login and other branded screens. Route-level code splitting exists, but it does not reduce this image.

Required correction: provide an appropriately sized optimized logo asset and verify actual page transfer sizes under throttled mobile conditions.

### 14. Low: The frontend quality-check command fails

Evidence: `frontend/src/components/chat/BusinessAiChatExperience.jsx:325`; `frontend/src/features/public/publicWebsiteShared.jsx:343`; `frontend/package.json`.

`npm run lint` reported four errors for unescaped quotation marks and 24 warnings. Consequently `npm run check`, which runs lint before build, fails. The standalone production build passes. Hook-dependency warnings need individual review; this report does not label every warning a proven runtime bug.

## Architecture and Implemented Coverage

| Area | What exists in the current code |
| --- | --- |
| Frontend | React 19, Vite, Tailwind, React Router lazy-loaded pages, React Query, owner/customer contexts and separate admin/customer/business layouts. |
| Backend | FastAPI routes under `/api/v1`, Pydantic request schemas, service modules, JWT authentication, role and tenant guards, MongoDB through Motor. |
| Business foundation | Tenant profiles, categories, custom fields, module dependencies, plan restrictions, package approval and website approval. |
| Catalog | Products, services, bundles/packages, variants, stock fields, images, categories and Excel import. |
| Public website | Shared configurable website layouts, catalog, item detail, about/contact pages, public chat and requests/orders. |
| Customer portal | Email/password registration and login, marketplace, favorites, cart, orders, payment proof/checkout flows and notifications. |
| AI | Explicit language, safety, catalog, intent, retrieval, draft-order and response stages; hosted model calls and deterministic fallback replies. |
| Retrieval | Mongo knowledge documents, file extraction, chunking, tenant Chroma collections, hosted embeddings or local hashed vectors, hybrid retrieval. |
| Orders | Draft confirmation, transaction types/statuses, inventory reserve/deduct/restore and notifications. |
| Payments | COD/manual verification, Stripe, JazzCash/Easypaisa adapters and simulator flows. Live settlement was not tested. |
| WhatsApp | Separate Node companion-device bridge, per-tenant sessions, discovery, pairing and inbound-message handoff to the API. |
| Insights | General analytics, report snapshots, delivery settings/manual sends, owner question classification and generated report sections. |
| Delivery tooling | Dockerfiles/Compose, demo and maintenance scripts, CI, readiness/QA/submission screens and documentation. |

Source anchors: `frontend/src/app/router.jsx`, `backend/app/api/v1/router.py`, `backend/app/services/`, `backend/app/ai/agents/orchestrator_agent.py`, `whatsapp-bridge/src/index.js`.

The main business flow is owner registration -> tenant/category setup -> catalog import -> module configuration -> website review -> admin approval -> public/customer shopping -> order/payment/inventory -> notifications and reports.

## Proposal Completion Estimate

My assessment is approximately **65% complete against the original proposal**, with a reasonable uncertainty range of **60-70%**. This is an evidence-weighted engineering estimate, not measured test coverage, a university grade, or a claim that 65% of every module works.

The proposal does not assign numerical weights. The following weights make the estimate transparent. Points award partial credit for working foundations while retaining deductions for missing automation, confirmed defects and unverified end-to-end behavior.

| Proposal requirement | Weight | Credit | Assessment |
| --- | ---: | ---: | --- |
| Web platform and business foundation | 10 | 9 | Substantial implementation; authentication/session issues remain. |
| Simple onboarding | 8 | 6 | Forms/wizard exist; timed nontechnical-user acceptance is unverified. Email replaces the original phone-first choice. |
| Excel product/service upload and catalog | 10 | 8.5 | Import and generalized catalog exist; large-file and real business data acceptance remain unverified. |
| Category-specific website generation | 12 | 9 | Configurable templates and category hints exist; much rendering is shared, and publication now requires approval. |
| Roman Urdu chat and RAG | 15 | 10.5 | Retrieval, hosted responses, language handling and drafts exist; natural conversation accuracy and provider-failure behavior need evaluation. |
| LangGraph multi-agent coordination | 10 | 3 | Explicit tool stages exist, but not the proposed LangGraph workflow or coordinated onboarding/website agents. |
| Orders, live stock and notifications | 10 | 6.5 | Substantial workflows; reproduced inventory defects and incomplete external-notification automation. |
| JazzCash, Easypaisa and COD | 8 | 4.8 | COD/manual flows and gateway code exist; simulator success is not evidence of merchant settlement. |
| Daily insights and automatic delivery | 7 | 3.15 | Dashboards/manual reports exist; wrong reporting scope and missing scheduling reduce completion. |
| Affordable recurring subscriptions | 4 | 1.6 | Plan/module approvals exist; inspected upgrade flow is `mock_manual`, not recurring subscription billing. |
| Mobile and low-bandwidth experience | 3 | 1.5 | Responsive classes and route splitting exist; oversized logo and no measured 2G/3G acceptance. |
| Testing, optimization and deployment | 3 | 1.5 | Tests, CI and containers exist; lint failures, live integration/UAT/deployment evidence remain unresolved. |
| **Total** | **100** | **65.05** | **Rounded assessment: 65%.** |

### Important proposal differences

1. **LangGraph is not integrated.** The orchestrator calls itself a deterministic, LangGraph-ready layer. No LangGraph dependency/import or StateGraph implementation was found in the searched application. Renaming tool stages as agents does not complete this explicit technology commitment.
2. **The default Groq model differs from Llama 3.** `backend/app/core/config.py` defaults to `openai/gpt-oss-20b`. Configuration may override it; the actual live provider/model was not verified. The methodology should match whichever model is actually used.
3. **Email registration is a deliberate later requirement.** The proposal says mobile-number signup. Your later request changed that, so email-only registration is not classified as a bug. Update the written scope with your supervisor. Customer email registration currently creates an unverified email account; email signup and proof of email ownership are separate requirements.
4. **Admin approval changes the 15-minute publication promise.** The proposal describes immediate automatic publication with zero human intervention. Your later approval requirement is implemented, but public availability now depends on an administrator. Define the promise as time to create/submit a site, or establish an approval service target.
5. **Plans are not a complete subscription system.** A paid label plus admin approval does not implement monthly billing, renewals, cancellation, expiry and payment reconciliation.
6. **A generic category theme is partial category specialization.** Restaurant, pharmacy and retail category definitions exist. The proposal's pharmacy-specific medicine-search/stock experience and retail filtering need dedicated acceptance demonstrations, not only category names and colors.
7. **No credit is withheld for out-of-scope features.** Native apps, delivery rider tracking, hardware POS integrations, advanced ERP and voice/video generation were explicitly excluded from the proposal.

## Verification Performed

| Check | Result |
| --- | --- |
| Backend unittest discovery | **268 tests passed**. |
| Frontend production build | **Passed**; 1,928 modules transformed. |
| Frontend lint | **Failed: 4 errors, 24 warnings**. |
| Backend Ruff lint | Could not run: Ruff is not installed in the backend virtual environment. |
| WhatsApp bridge syntax | Both `src/index.js` and `src/tenants.js` passed `node --check`. |
| Long-password reproduction | Policy accepted 80 characters; installed bcrypt raised ValueError. |
| Inventory reservation reproduction | Service accepted 8 reserved units against 5 available units using isolated mock data. |
| Inventory restore reproduction | Restoring a deducted order incorrectly reduced another reservation from 3 to 1. |

The reproductions used mock database objects; they did not alter business records. No application source was changed. This report is the only intentional new source-controlled artifact from the review; builds/tests may generate ignored output.

The review mapped the repository and inspected representative critical paths across authentication, tenancy, publication, orders, inventory, payments, reporting, AI/retrieval and the bridge. It is not a claim that every line or screen was exhaustively exercised, or that these are all possible bugs.

Not performed: real MongoDB concurrency testing, live SMTP delivery, real WhatsApp pairing/messages, merchant sandbox/live transactions, hosted AI quality evaluation, browser end-to-end tests, mobile screenshots, load tests, or deployed-environment checks. The proposal's bibliography and market statistics were not fact-checked. Secrets from environment files were not reproduced in this report.

## Further Verification Risks

- Embedding generation can fall back from a hosted vector to a 384-dimensional local hash vector while retaining the same tenant collection name (`rag_embedding_service.py`, `rag_vector_service.py`). Provider changes/outages need an isolated integration test for dimensional consistency, reindexing and fallback retrieval. This was not reproduced against a live Chroma collection here.
- Chroma persistence defaults to a directory in the backend container, while Compose persists uploads and logs but not a dedicated Chroma volume. Check persistence across container replacement; Mongo knowledge documents are not the same as a preserved vector index.
- Public item search passes user search text directly to Mongo `$regex`. Literal brackets or regex metacharacters need invalid-pattern and bounded-performance tests.
- Current tests are heavily based on mocked service data. Passing tests do not establish database atomicity, external integration delivery, or correct browser navigation.
- README phase/completion claims and internal submission/readiness scores are application content, not independent evidence that proposal acceptance criteria have passed.

## Recommended Work Order

1. Protect WhatsApp pairing/reset, revoke sessions on credential changes, and remove startup password overwrites.
2. Correct inventory reservation/restoration and add database-backed concurrent-order tests.
3. Correct password byte-length handling and restrict public tenant/proof exposure.
4. Fix date-scoped reports and local timezone handling; implement scheduled execution and delivery idempotency.
5. Resolve launch-status inconsistencies and frontend lint failures; optimize the shared logo.
6. Implement the promised LangGraph coordination, or formally revise the methodology if the deterministic pipeline is the agreed architecture.
7. Demonstrate local payment sandbox/merchant integration, real report delivery and supported AI behavior, including failures.
8. Run timed owner onboarding and restaurant/pharmacy/retail acceptance tests on mobile/slow-network conditions; record results and update the proposal traceability document.

To close the unverified gaps, useful evidence would be approved scope revisions, sandbox merchant test access, an isolated test database, a test WhatsApp business number, redacted deployment configuration, provider delivery results and representative Roman Urdu conversations. Do not put passwords, OTPs or secret keys into the report or chat.
