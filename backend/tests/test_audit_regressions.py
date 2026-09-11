import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from app.core.private_uploads import _signature, payment_record_view, ProtectedUploads
from app.core.public_views import customer_order_view, public_business_view
from app.core.security import create_access_token, create_refresh_token, decode_token, ensure_current_session, verify_password, hash_password, require_auth_in_production
from app.services.reporting_service import _parse_summary_date
from app.services.report_scheduler import report_is_due
from app.services.whatsapp_service import bridge_is_online, build_bridge_pairing_url


class AuditRegressionTests(unittest.TestCase):
    def test_overlong_password_never_reaches_bcrypt(self):
        with patch("app.core.security.bcrypt.checkpw") as check:
            self.assertFalse(verify_password("A9!" * 30, "hash"))
            self.assertFalse(verify_password("\u00e9" * 37, "hash"))
            check.assert_not_called()
        with self.assertRaises(HTTPException) as error:
            hash_password("A9!" * 30)
        self.assertEqual(error.exception.status_code, 422)

    def test_password_session_version_invalidates_access_and_refresh(self):
        user = {"_id": ObjectId(), "sessionVersion": 3}
        for creator, kind in ((create_access_token, "access"), (create_refresh_token, "refresh")):
            payload = decode_token(creator(user), kind)
            ensure_current_session(payload, user)
            with self.assertRaises(HTTPException):
                ensure_current_session(payload, {**user, "sessionVersion": 4})

    def test_public_business_excludes_owner_and_admin_review(self):
        result = public_business_view({"_id": ObjectId(), "name": "Shop", "ownerId": ObjectId(), "websiteApprovalNotes": "private", "settings": {"planCode": "scale", "packageAccess": {"secret": True}, "languageMode": "english"}})
        self.assertEqual(result["name"], "Shop")
        self.assertNotIn("ownerId", result)
        self.assertNotIn("websiteApprovalNotes", result)
        self.assertEqual(result["settings"], {"languageMode": "english"})

    def test_customer_order_hides_internal_inventory(self):
        result = customer_order_view({"_id": ObjectId(), "internalNotes": "private", "inventoryMovements": [{"actorUserId": ObjectId()}], "items": [{"costPrice": 12, "stockSnapshot": {"tracked": True, "availableQuantity": 15, "remainingAfter": 14, "available": True, "message": "15 available"}}]})
        self.assertNotIn("internalNotes", result)
        self.assertNotIn("inventoryMovements", result)
        self.assertNotIn("availableQuantity", result["items"][0]["stockSnapshot"])
        self.assertNotIn("15", result["items"][0]["stockSnapshot"]["message"])
        self.assertNotIn("costPrice", result["items"][0])

    def test_payment_proof_url_is_scoped_and_short_lived(self):
        tenant_id = ObjectId()
        path = f"/uploads/payment-proofs/{tenant_id}/order/proof.png"
        result = payment_record_view({"tenantId": tenant_id, "screenshotUrl": path})
        parsed = urlsplit(result["screenshotUrl"])
        query = parse_qs(parsed.query)
        self.assertEqual(query["grant"][0], _signature(path, int(query["expires"][0])))
        other = payment_record_view({"tenantId": ObjectId(), "screenshotUrl": path})
        self.assertEqual(other["screenshotUrl"], "")

    def test_private_upload_requires_a_valid_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            tenant = str(ObjectId())
            file = Path(directory) / "payment-proofs" / tenant / "order" / "proof.png"
            file.parent.mkdir(parents=True)
            file.write_bytes(b"test-proof")
            app = FastAPI()
            app.mount("/uploads", ProtectedUploads(directory=directory))
            path = f"/uploads/payment-proofs/{tenant}/order/proof.png"
            signed = payment_record_view({"tenantId": tenant, "screenshotUrl": path})["screenshotUrl"]
            with TestClient(app) as client:
                self.assertEqual(client.get(path).status_code, 403)
                valid = client.get(signed)
                self.assertEqual(valid.status_code, 200)
                self.assertEqual(valid.headers["cache-control"], "private, no-store")
                self.assertEqual(client.get(signed.replace("proof.png", "other.png")).status_code, 403)
                self.assertEqual(client.get(path + "?expires=1&grant=bad").status_code, 403)

    def test_daily_boundary_uses_pakistan_midnight(self):
        start = _parse_summary_date("2026-09-11")
        self.assertEqual(start.astimezone(timezone.utc).isoformat(), "2026-09-10T19:00:00+00:00")

    def test_scheduler_respects_saved_time_and_enabled_flag(self):
        config = {"enabled": True, "deliveryTime": "21:00", "timezone": "Asia/Karachi"}
        self.assertFalse(report_is_due(config, datetime(2026, 9, 11, 15, 59, tzinfo=timezone.utc)))
        self.assertTrue(report_is_due(config, datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc)))
        self.assertFalse(report_is_due({**config, "enabled": False}, datetime.now(timezone.utc)))

    def test_bridge_requires_a_recent_heartbeat(self):
        doc = {"isConnected": True, "bridgeStatus": "ready", "bridgeLastSeenAt": datetime.now(timezone.utc)}
        self.assertTrue(bridge_is_online(doc))
        self.assertFalse(bridge_is_online({**doc, "bridgeLastSeenAt": datetime.now(timezone.utc) - timedelta(minutes=5)}))
        self.assertFalse(bridge_is_online({**doc, "bridgeStatus": "disconnected"}))

    def test_pairing_link_does_not_expose_bridge_token(self):
        link = build_bridge_pairing_url(str(ObjectId()), "private-test-token")
        self.assertNotIn("private-test-token", link)
        self.assertIn("grant=", link)


class AsyncAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_seed_admin_is_never_overwritten(self):
        from app.db.seeders.seed_admin import seed_default_admin
        users = SimpleNamespace(find_one=AsyncMock(return_value={"_id": ObjectId(), "passwordHash": "existing"}), update_one=AsyncMock())
        with patch("app.db.seeders.seed_admin.get_database", return_value=SimpleNamespace(users=users)), patch("app.db.seeders.seed_admin.get_mongo_status", AsyncMock(return_value={"connected": True})):
            await seed_default_admin()
        users.find_one.assert_awaited_once()
        users.update_one.assert_not_called()

    async def test_report_is_queued_but_inbound_reply_is_not_queued_twice(self):
        from app.integrations.whatsapp.provider import send_whatsapp_text
        logs = SimpleNamespace(insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId())))
        with patch("app.integrations.whatsapp.provider.get_database", return_value=SimpleNamespace(whatsapp_message_logs=logs)):
            report = await send_whatsapp_text(tenant_id=ObjectId(), provider="baileys", to_phone="+923001234567", message_text="Test", raw_context={"source": "daily_report_delivery"})
            reply = await send_whatsapp_text(tenant_id=ObjectId(), provider="baileys", to_phone="+923001234567", message_text="Test", raw_context={"source": "whatsapp_agent_auto_reply"})
        self.assertEqual(report["deliveryStatus"], "queued")
        self.assertEqual(reply["deliveryStatus"], "returned_to_bridge")

    async def test_diagnostics_reject_regular_users(self):
        with patch("app.core.security.get_authenticated_user", AsyncMock(return_value={"globalRole": "user"})):
            with self.assertRaises(HTTPException) as error:
                await require_auth_in_production(HTTPAuthorizationCredentials(scheme="Bearer", credentials="test"))
        self.assertEqual(error.exception.status_code, 403)

    async def test_stock_answer_uses_live_catalog_without_model(self):
        from app.ai.agents.tools import generate_agent_response
        with patch("app.ai.agents.tools.generate_openai_response", AsyncMock()) as model:
            response, source = await generate_agent_response({}, "Grey Tracksuit available?", [], "english", {"intent": "ask_availability"}, [{"content": "16 left"}], {}, [{"name": "Grey Tracksuit", "price": 4800, "isStockTracked": True, "stock": {"quantity": 14, "reservedQuantity": 3}}], {"allowed": True})
        self.assertEqual(source, "live_catalog")
        self.assertIn("In stock", response)
        self.assertNotIn("16", response)
        model.assert_not_called()
