from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.owner_agent_schema import OwnerAgentChatRequest
from app.services.owner_agent_service import chat_with_owner_agent, get_owner_agent_history, get_owner_agent_insights

router = APIRouter(prefix="/tenants/{tenantId}/owner-agent", tags=["owner-agent"])


@router.get("/insights")
async def insights(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_owner_agent_insights(tenantId, current_user)
    return success_response("Owner agent insights fetched successfully.", data)


@router.post("/chat")
async def chat(tenantId: str, payload: OwnerAgentChatRequest, current_user: dict = Depends(get_current_business_user)):
    data = await chat_with_owner_agent(tenantId, payload, current_user)
    return success_response("Owner agent replied successfully.", data)


@router.get("/history")
async def history(
    tenantId: str,
    limit: int = Query(default=30, ge=1, le=100),
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_owner_agent_history(tenantId, current_user, limit=limit)
    return success_response("Owner agent history fetched successfully.", data["items"], {"tenant": data["tenant"], "conversationId": data["conversationId"]})
