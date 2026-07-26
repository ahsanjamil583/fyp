from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.knowledge_base_schema import KnowledgeBaseTestQuestionRequest, KnowledgeDocumentUpdateRequest, KnowledgeTextCreateRequest
from app.services.knowledge_base_service import (
    create_text_knowledge_document,
    delete_knowledge_document,
    get_knowledge_document,
    list_knowledge_documents,
    reindex_knowledge_base_for_owner,
    test_knowledge_base_question,
    update_knowledge_document,
    upload_knowledge_document,
)

router = APIRouter(prefix="/tenants/{tenantId}/knowledge-base", tags=["knowledge-base"])


@router.get("")
async def list_documents(
    tenantId: str,
    search: str = "",
    sourceType: str | None = Query(default=None),
    activeOnly: bool = False,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_knowledge_documents(tenantId, current_user, search, sourceType, activeOnly, page, limit)
    return success_response("Knowledge documents fetched successfully.", data["items"], data["pagination"] | {"summary": data["summary"], "tenant": data["tenant"]})


@router.post("/text")
async def create_text_document(tenantId: str, payload: KnowledgeTextCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_text_knowledge_document(tenantId, payload, current_user)
    return success_response("Knowledge text document created successfully.", data)


@router.post("/upload")
async def upload_document(
    tenantId: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    moduleCode: str = Form(default="ai_chat"),
    tags: str = Form(default=""),
    isActive: bool = Form(default=True),
    current_user: dict = Depends(get_current_business_user),
):
    data = await upload_knowledge_document(tenantId, file, current_user, title, moduleCode, tags, isActive)
    return success_response("Knowledge document uploaded and indexed successfully.", data)


@router.post("/reindex")
async def reindex_documents(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await reindex_knowledge_base_for_owner(tenantId, current_user)
    return success_response("Knowledge base reindexed successfully.", data)


@router.post("/test-question")
async def test_question(tenantId: str, payload: KnowledgeBaseTestQuestionRequest, current_user: dict = Depends(get_current_business_user)):
    data = await test_knowledge_base_question(tenantId, payload, current_user)
    return success_response("Knowledge base test answer generated successfully.", data)


@router.get("/{documentId}")
async def get_document(tenantId: str, documentId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_knowledge_document(tenantId, documentId, current_user)
    return success_response("Knowledge document fetched successfully.", data)


@router.put("/{documentId}")
async def update_document(tenantId: str, documentId: str, payload: KnowledgeDocumentUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_knowledge_document(tenantId, documentId, payload, current_user)
    return success_response("Knowledge document updated and indexed successfully.", data)


@router.delete("/{documentId}")
async def delete_document(tenantId: str, documentId: str, current_user: dict = Depends(get_current_business_user)):
    data = await delete_knowledge_document(tenantId, documentId, current_user)
    return success_response("Knowledge document deleted successfully.", data)
