import hashlib
import hmac
import time
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.object_ids import serialize_document


def _signature(path: str, expires: int) -> str:
    return hmac.new(settings.jwt_secret_key.encode(), f"proof:{path}:{expires}".encode(), hashlib.sha256).hexdigest()


def payment_record_view(record: dict | None) -> dict | None:
    if record is None:
        return None
    result = serialize_document(record)
    path = urlsplit(result.get("screenshotUrl") or "").path
    prefix = f"/uploads/payment-proofs/{record.get('tenantId')}/"
    if path.startswith("/uploads/payment-proofs/"):
        if not path.startswith(prefix) or ".." in path or "\\" in path:
            result["screenshotUrl"] = ""
        else:
            expires = int(time.time()) + 600
            result["screenshotUrl"] = f"{path}?expires={expires}&grant={_signature(path, expires)}"
    return result


class ProtectedUploads(StaticFiles):
    async def get_response(self, path: str, scope):
        base = Path(self.directory).resolve()
        resolved = (base / path).resolve()
        try:
            relative = resolved.relative_to(base)
        except ValueError:
            raise HTTPException(status_code=404)
        if relative.parts and relative.parts[0].lower() == "payment-proofs":
            query = parse_qs(scope.get("query_string", b"").decode())
            raw_expiry = query.get("expires", [""])[0]
            grant = query.get("grant", [""])[0]
            expires = int(raw_expiry) if raw_expiry.isdigit() and len(raw_expiry) <= 12 else 0
            now = int(time.time())
            canonical = "/uploads/" + relative.as_posix()
            if not (now < expires <= now + 600 and re.fullmatch(r"[a-f0-9]{64}", grant) and hmac.compare_digest(grant, _signature(canonical, expires))):
                raise HTTPException(status_code=403, detail="Open the payment proof from your signed-in account.")
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        return await super().get_response(path, scope)


def customer_payment_result(data: dict) -> dict:
    from app.core.public_views import customer_order_view
    result = dict(data)
    if isinstance(result.get("transaction"), dict):
        result["transaction"] = customer_order_view(result["transaction"])
    if isinstance(result.get("payment"), dict):
        result["payment"] = payment_record_view(result["payment"])
        for field in ("actorUserId", "createdBy", "updatedBy", "verifiedBy", "internalNotes", "providerResponse", "gatewayResponse"):
            result["payment"].pop(field, None)
    return result
