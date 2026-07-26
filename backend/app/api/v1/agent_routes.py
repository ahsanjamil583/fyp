from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.agent_schema import AgentPreviewRequest
from app.services.agent_tool_service import get_agent_tool_catalog, preview_agent_run

router = APIRouter(prefix="/tenants/{tenantId}/agent", tags=["agent-tools"])


@router.get("/tools")
async def tools(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_agent_tool_catalog(tenantId, current_user)
    return success_response("Agent tool catalog fetched successfully.", data)


@router.post("/preview")
async def preview(tenantId: str, payload: AgentPreviewRequest, current_user: dict = Depends(get_current_business_user)):
    data = await preview_agent_run(tenantId, payload, current_user)
    return success_response("Agent preview completed successfully.", data)
