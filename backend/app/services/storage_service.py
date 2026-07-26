from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


async def store_item_image(tenant_id: str, item_id: str, file: UploadFile) -> dict:
    extension = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only JPG, PNG, WEBP, and GIF images are allowed.")

    base_dir = Path(settings.local_upload_dir).resolve()
    item_dir = base_dir / "items" / tenant_id / item_id
    item_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid4().hex}{extension}"
    destination = item_dir / file_name
    size = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 5 * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image must be 5MB or smaller.")
            output.write(chunk)

    relative_path = f"items/{tenant_id}/{item_id}/{file_name}"
    return {
        "provider": "local",
        "fileId": relative_path,
        "url": f"/uploads/{relative_path}",
    }


async def store_payment_proof_image(tenant_id: str, transaction_id: str, file: UploadFile) -> dict:
    extension = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only JPG, PNG, WEBP, and GIF proof images are allowed.")

    base_dir = Path(settings.local_upload_dir).resolve()
    proof_dir = base_dir / "payment-proofs" / tenant_id / transaction_id
    proof_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid4().hex}{extension}"
    destination = proof_dir / file_name
    size = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 5 * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payment proof image must be 5MB or smaller.")
            output.write(chunk)

    relative_path = f"payment-proofs/{tenant_id}/{transaction_id}/{file_name}"
    return {
        "provider": "local",
        "fileId": relative_path,
        "url": f"/uploads/{relative_path}",
    }
