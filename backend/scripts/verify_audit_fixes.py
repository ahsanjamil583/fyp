"""Read-only live regression checks. Login credentials arrive on stdin, never in artifacts."""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings


def main():
    credentials = json.load(sys.stdin)
    records = []
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60)

    def check(name, path, token=None, method="GET", payload=None, expected=200):
        response = client.request(method, path, json=payload, headers={"Authorization": f"Bearer {token}"} if token else {})
        records.append({"test": name, "path": path, "status": response.status_code, "expected": expected, "pass": response.status_code == expected})
        return response.json().get("data") if response.headers.get("content-type", "").startswith("application/json") else None

    tokens = {}
    for role, cred in credentials.items():
        path = "/api/v1/customer/auth/login" if role == "customer" else "/api/v1/auth/login"
        result = check(role + " login", path, method="POST", payload=cred)
        tokens[role] = result["accessToken"]
    tenant = check("Owner tenants", "/api/v1/tenants/my", tokens["business"])[0]
    tid, slug = tenant["id"], tenant["slug"]
    check("Anonymous diagnostics blocked", "/api/v1/health/readiness", expected=401)
    check("Owner diagnostics blocked", "/api/v1/health/readiness", tokens["business"], expected=403)
    check("Demo credentials blocked", "/api/v1/health/demo-accounts", expected=401)
    check("Literal bracket public search", f"/api/v1/public/businesses/{slug}/items?search=%5B")
    check("Literal bracket owner search", f"/api/v1/tenants/{tid}/items?search=%5B", tokens["business"])
    check("Overlong login password handled", "/api/v1/auth/login", method="POST", payload={"email": credentials["business"]["email"], "password": "Aa9!" * 20}, expected=401)
    business = check("Public business", f"/api/v1/public/businesses/{slug}")
    records.append({"test": "Public metadata privacy", "pass": not any(k in business for k in ("ownerId", "ownerUserId", "websiteApprovalNotes")) and "packageAccess" not in business.get("settings", {})})
    orders = check("Customer orders", "/api/v1/customer/orders", tokens["customer"])
    for order in orders[:2]:
        detail = check("Customer order detail", f"/api/v1/customer/orders/{order['id']}", tokens["customer"])
        records.append({"test": "Order privacy", "pass": not any(k in detail for k in ("internalNotes", "inventoryMovements", "inventoryMovementsDetailed"))})
    whatsapp = check("Owner WhatsApp status", f"/api/v1/tenants/{tid}/whatsapp/settings", tokens["business"])
    state = whatsapp["settings"]
    records.append({"test": "WhatsApp wiring", "bridgeOnline": state.get("bridgeOnline"), "signedPairingLink": "grant=" in state.get("bridgePairingUrl", ""), "sameOriginLink": state.get("bridgePairingUrl", "").startswith("/whatsapp-bridge/")})
    if state.get("bridgePairingUrl", "").startswith("/whatsapp-bridge/"):
        response = client.get("http://localhost:5173" + state["bridgePairingUrl"])
        records.append({"test": "Authenticated dashboard pairing link", "status": response.status_code, "pass": response.status_code == 200})
        response = client.post(f"http://localhost:5173/whatsapp-bridge/pair/{tid}/reset")
        records.append({"test": "Anonymous pairing reset blocked", "status": response.status_code, "pass": response.status_code == 403})
    preview = check("Live catalog AI answer", f"/api/v1/tenants/{tid}/agent/preview", tokens["business"], method="POST", payload={"messageText": "Is Grey Tracksuit available?", "channel": "customer_portal", "includeRecentMessages": False})
    records.append({"test": "AI current-stock reply", "reply": preview.get("reply"), "meta": preview.get("meta")})
    report = check("Report settings", f"/api/v1/tenants/{tid}/reports/delivery/settings", tokens["business"])
    if report:
        records.append({"test": "Scheduler runtime", "enabled": report.get("settings", {}).get("schedulerActive")})
    logs = check("Report delivery logs", f"/api/v1/tenants/{tid}/reports/delivery/logs", tokens["business"])
    records.append({"test": "Recent report delivery", "logs": [{k: row.get(k) for k in ("summaryDate", "channel", "deliveryStatus")} for row in logs[:3]]})
    check("Unsigned proof blocked", "/uploads/payment-proofs/test/test.png", expected=403)
    for path in ("/api/v1/health", "/", "/.env"):
        response = client.get("http://localhost:5173" + path)
        records.append({"test": "Frontend proxy/files", "path": path, "status": response.status_code, "privateEnvExposed": "JWT_SECRET_KEY=" in response.text or "VITE_API_BASE_URL=" in response.text})
    admin = check("Admin login", "/api/v1/auth/login", method="POST", payload={"email": settings.default_admin_email, "password": settings.default_admin_password})
    if admin:
        records.append({"test": "Admin policy gate", "mustResetPassword": admin.get("user", {}).get("mustResetPassword"), "role": admin.get("user", {}).get("globalRole")})
    output = Path(__file__).resolve().parents[2] / "docs" / "audit-fixes-verification.json"
    output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
