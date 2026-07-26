from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.qa_schema import QaDemoRunRequest
from app.services.qa_service import build_tenant_qa_report, record_demo_run

router = APIRouter(prefix="/tenants/{tenantId}/qa", tags=["final-qa"])


@router.get("/checklist")
async def qa_checklist(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await build_tenant_qa_report(tenantId, current_user)
    return success_response("Final QA checklist generated successfully.", data)


@router.post("/demo-run")
async def qa_demo_run(tenantId: str, payload: QaDemoRunRequest, current_user: dict = Depends(get_current_business_user)):
    data = await record_demo_run(tenantId, payload, current_user)
    return success_response("Demo QA run recorded successfully.", data)
