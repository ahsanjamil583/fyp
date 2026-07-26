from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.customer_portal_schema import CustomerChatMessageRequest
from app.services.ai_chat_service import get_owner_conversation_detail, list_owner_conversations
from app.services.rag_index_service import get_tenant_rag_status, reindex_tenant_knowledge_for_owner

router = APIRouter(prefix="/tenants/{tenantId}/ai", tags=["ai-chat"])


@router.get("/conversations")
async def conversations(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await list_owner_conversations(tenantId, current_user)
    return success_response("AI conversations fetched successfully.", data)


@router.get("/conversations/{conversationId}")
async def conversation_detail(tenantId: str, conversationId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_owner_conversation_detail(tenantId, conversationId, current_user)
    return success_response("AI conversation fetched successfully.", data)


@router.get("/rag/status")
async def rag_status(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_tenant_rag_status(tenantId, current_user)
    return success_response("RAG status fetched successfully.", data)


@router.post("/rag/reindex")
async def rag_reindex(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await reindex_tenant_knowledge_for_owner(tenantId, current_user)
    return success_response("RAG reindex completed successfully.", data)
