# Phase 21: Knowledge Base Manager

Phase 21 adds an owner-facing Knowledge Base Manager for RAG. Business owners can upload or write business knowledge, and BizXus AI indexes that content into the existing tenant Chroma collection.

## Implemented backend files

- `backend/app/api/v1/knowledge_base_routes.py`
- `backend/app/services/knowledge_base_service.py`
- `backend/app/schemas/knowledge_base_schema.py`

## Implemented frontend files

- `frontend/src/features/dashboard/KnowledgeBasePage.jsx`
- `frontend/src/services/knowledgeBaseApi.js`

## API endpoints

All routes require a business owner token and the tenant `ai_chat` module must be enabled.

- `GET /api/v1/tenants/{tenantId}/knowledge-base`
- `POST /api/v1/tenants/{tenantId}/knowledge-base/text`
- `POST /api/v1/tenants/{tenantId}/knowledge-base/upload`
- `GET /api/v1/tenants/{tenantId}/knowledge-base/{documentId}`
- `PUT /api/v1/tenants/{tenantId}/knowledge-base/{documentId}`
- `DELETE /api/v1/tenants/{tenantId}/knowledge-base/{documentId}`
- `POST /api/v1/tenants/{tenantId}/knowledge-base/reindex`

## Supported upload formats

- `.txt`
- `.md`
- `.csv`
- `.xlsx`
- `.xlsm`
- `.pdf`
- `.docx`

Maximum upload size is 10MB. Extracted text is capped to keep RAG documents manageable.

## RAG behavior

Owner documents are stored in `knowledge_documents` using:

- `sourceType: owner_text`
- `sourceType: owner_upload`

Uploaded and manually written documents are indexed with the existing `upsert_knowledge_document_vectors()` function, so the current customer/public AI chat can retrieve them through `hybrid_retrieve_knowledge()`.

## Frontend route

The page is available at:

```text
/dashboard/knowledge-base
```

It appears in the dashboard navigation when the `ai_chat` module is enabled.

## Required dependency update

Run this after pulling the phase:

```bash
cd backend
pip install -r requirements.txt
```

The new dependencies are:

- `pypdf`
- `python-docx`

## Test checklist

1. Enable the AI Chat module for a tenant.
2. Open `/dashboard/knowledge-base`.
3. Add a text FAQ, for example delivery timing or refund policy.
4. Upload a TXT/PDF/DOCX/XLSX file.
5. Confirm document count and chunk count update.
6. Ask the customer chatbot a question related to the uploaded knowledge.
7. Confirm the AI answer uses the uploaded knowledge source.
8. Edit a knowledge document and confirm it reindexes.
9. Disable a document and confirm it is no longer active in RAG.
10. Delete an owner document and confirm it is removed.
