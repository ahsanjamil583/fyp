# Audit Fixes and Verification

## Completed

- Replaced the known local JWT signing key without exposing its replacement. Existing sessions must log in again.
- Disabled public stack traces and restricted diagnostic/demo-account endpoints to platform admins, including in development behind ngrok.
- Password changes/resets now increment a session version, invalidating old access and refresh tokens. Overlong bcrypt inputs return validation/authentication errors instead of HTTP 500.
- Startup admin seeding no longer overwrites an existing account's password, role, or status.
- Public business and customer-order responses exclude owner/admin metadata and internal inventory history. Customer payment responses are sanitized.
- Payment-proof URLs require a path-scoped, ten-minute signed grant issued through authenticated payment views. Unsigned static URLs return 403.
- Search input is treated literally, preventing regex syntax crashes in public, customer, catalog, transaction, and knowledge searches.
- Customer price/availability answers use the live catalog, excluding stale indexed item documents and private stock counts.
- Stock changes use MongoDB compare-and-swap updates and persisted per-order claims. Duplicate lines are combined; partial reservations are compensated. Refunding deducted stock leaves other orders' reservations unchanged.
- Transaction status updates reject concurrent edits and roll back the status when inventory processing fails.
- Daily reports now scope revenue, top items, and recent transactions to the selected date in the configured timezone. Legacy cached summaries are regenerated.
- Launch finalization reflects the actual website review/publication state.
- Frontend API/upload paths use the same-origin Vite proxy. Pairing pages are also available through that proxy for a single ngrok tunnel.
- WhatsApp pairing/reset pages require short-lived tenant-scoped grants. The dashboard polls heartbeat-derived connection status without overwriting unsaved form input.
- Added an authenticated outbound queue for standalone WhatsApp reports/test messages. Existing inbound replies are not sent twice.
- Added a timezone-aware daily scheduler with persisted duplicate-attempt prevention. Enabled the scheduler locally following explicit user confirmation.
- Fixed lint errors and the mixed-export Fast Refresh issue. Added an unavailable-image fallback for absent product uploads.
- Updated frontend dependencies; npm audit reports zero vulnerabilities. Added the timezone database required on Windows.

## Evidence

- `audit-fixes-verification.json`: live login, search, privacy, signed pairing, anonymous reset denial, live-stock AI answer, same-origin API, and scheduler checks.
- `backend/tests/test_audit_regressions.py`: authentication, privacy, signed uploads, stock answers, scheduler time, and bridge heartbeat tests.
- `backend/tests/test_inventory_mongo_regressions.py`: real Mongo concurrency, rollback, refund, daily-report, scheduler ownership, duplicate-run, and outbound queue checks. These use new disposable databases, never business inventory.
- `whatsapp-bridge/src/pairing-auth.test.js`: five passing grant-validation tests.
- Full backend suite: 292 tests pass, including the opt-in real Mongo regression tests.
- Frontend `npm run check` passes. There are still 24 existing lint warnings; these are not reported as fixed.

## Runtime and Remaining Requirements

- Frontend: http://localhost:5173/ . Backend: http://127.0.0.1:8000/ . The bridge was started using the existing configuration/session, without resetting credentials; the business reports online.
- Admin login works, but its `mustResetPassword` security gate remains. Complete the required password change to use normal admin endpoints.
- Automatic scheduling is enabled. Following explicit user confirmation, the business schedule was saved for its existing WhatsApp number at 21:00 Asia/Karachi, with SMS disabled. The scheduler queued the September 11 report and the bridge acknowledged it as `sent`. This confirms the bridge send operation, not a recipient read receipt.
- The seven missing product images were not recoverable from the workspace. Re-upload their originals; the UI now handles missing files gracefully. The existing large logo asset remains unoptimized.
- Browser automation still has no connected browser. HTTP/API checks and builds passed; visual layout and end-to-end browser interaction are not verified.
- Persisted inventory/message claims deliberately remain for reconciliation after a process crash or ambiguous network result. This avoids blind retries and duplicate stock changes/messages; it is not a distributed exactly-once guarantee.
- Keep MongoDB, the backend, and the WhatsApp bridge running for scheduled delivery. ngrok only exposes the application; it does not keep these processes running.

## Ngrok Configuration

Set `VITE_API_BASE_URL=/api/v1` and the exact ngrok hostname in `frontend/.env.local`, using `frontend/.env.example` as the reference. Restart Vite after changing the hostname. Do not expose MongoDB or use `allowedHosts=true`.

```powershell
cd C:\Users\ahsan\Desktop\BIZXUSAI\phase-32\bizxus-code\frontend
$env:NGROK_HOST = 'YOUR-ASSIGNED-HOST.ngrok-free.app'
npm run dev
```

Point the tunnel to port 5173. API, uploads, and authenticated pairing pages are forwarded locally. The ngrok hostname has not been supplied or publicly tested yet. Restart the existing Vite process before tunneling so its updated dependencies are loaded.

## Repeat Verification

```powershell
cd C:\Users\ahsan\Desktop\BIZXUSAI\phase-32\bizxus-code\backend
$env:REPORT_SCHEDULER_ENABLED = 'false'
$env:RUN_MONGO_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The scheduler override is for the test process. The local `.env` retains the user's enabled scheduler setting.
