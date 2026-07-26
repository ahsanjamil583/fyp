from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.submission_schema import SubmissionSignoffRequest
from app.services.submission_service import build_submission_package, build_tenant_export_snapshot, record_submission_signoff

router = APIRouter(prefix="/tenants/{tenantId}/submission", tags=["submission-center"])


@router.get("/package")
async def submission_package(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await build_submission_package(tenantId, current_user)
    return success_response("Submission package generated successfully.", data)


@router.get("/export")
async def submission_export(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await build_tenant_export_snapshot(tenantId, current_user)
    return success_response("Tenant submission snapshot generated successfully.", data)


@router.post("/signoff")
async def submission_signoff(tenantId: str, payload: SubmissionSignoffRequest, current_user: dict = Depends(get_current_business_user)):
    data = await record_submission_signoff(tenantId, payload, current_user)
    return success_response("Submission sign-off recorded successfully.", data)
