from datetime import datetime, timezone

from bson import ObjectId

from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.rag_vector_service import rebuild_tenant_vector_index, upsert_knowledge_document_vectors


async def _upsert_knowledge_document(
    tenant_id: ObjectId,
    source_type: str,
    source_id: ObjectId,
    module_code: str,
    title: str,
    content: str,
    metadata: dict,
    is_active: bool,
) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    chroma_document_id = f"{source_type}_{source_id}"
    await db.knowledge_documents.update_one(
        {"tenantId": tenant_id, "sourceType": source_type, "sourceId": source_id},
        {
            "$set": {
                "tenantId": tenant_id,
                "branchId": None,
                "moduleCode": module_code,
                "sourceType": source_type,
                "sourceId": source_id,
                "title": title,
                "content": content,
                "chromaCollection": f"tenant_{tenant_id}",
                "chromaDocumentId": chroma_document_id,
                "metadata": metadata,
                "isActive": is_active,
                "updatedAt": now,
            },
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
    )
    document = await db.knowledge_documents.find_one({"tenantId": tenant_id, "sourceType": source_type, "sourceId": source_id})
    vector_result = await upsert_knowledge_document_vectors(document)
    await db.knowledge_documents.update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "embeddingProvider": vector_result["embeddingProvider"],
                "chunkCount": vector_result["chunkCount"],
                "lastIndexedAt": now,
            }
        },
    )
    return await db.knowledge_documents.find_one({"_id": document["_id"]})


async def index_item_for_rag(tenant_id: ObjectId, item: dict) -> None:
    content_parts = [
        item.get("name", ""),
        item.get("description", ""),
        " ".join(item.get("tags", [])),
        f"Type: {item.get('itemType', '')}",
        f"Price: {item.get('price', 0)} {item.get('currency', 'PKR')}",
        (
            f"Service duration: {item.get('serviceDetails', {}).get('durationMinutes', 0)} minutes"
            if item.get("serviceDetails", {}).get("durationMinutes")
            else ""
        ),
        (
            "Variants: " + ", ".join(
                " | ".join(
                    part
                    for part in [
                        f"name {variant.get('name', '')}",
                        f"sku {variant.get('sku', '')}" if variant.get("sku") else "",
                        f"price {variant.get('price', 0)} {item.get('currency', 'PKR')}",
                        f"stock {variant.get('stockQuantity', 0)}",
                        "options " + " ".join(f"{key}: {value}" for key, value in (variant.get("optionValues") or {}).items()),
                    ]
                    if part
                )
                for variant in item.get("variants", [])
                if variant.get("isActive", True)
            )
            if item.get("variants")
            else ""
        ),
        (
            "Custom fields: " + " ".join(f"{key}: {value}" for key, value in (item.get("customFields") or {}).items())
            if item.get("customFields")
            else ""
        ),
        (
            f"Stock: quantity {item.get('stock', {}).get('quantity', 0)}, reserved {item.get('stock', {}).get('reservedQuantity', 0)}, low threshold {item.get('stock', {}).get('lowStockThreshold', 0)}"
            if item.get("stock")
            else ""
        ),
        (
            "Bundle components: " + ", ".join(component.get("itemName", "") for component in item.get("bundleComponents", []))
            if item.get("bundleComponents")
            else ""
        ),
    ]
    content = "\n".join(part for part in content_parts if part)

    await _upsert_knowledge_document(
        tenant_id=tenant_id,
        source_type="item",
        source_id=item["_id"],
        module_code="items",
        title=item.get("name", "Item"),
        content=content,
        metadata={
            "itemType": item.get("itemType"),
            "status": item.get("status"),
            "isSellable": item.get("isSellable"),
            "isBookable": item.get("isBookable"),
        },
        is_active=item.get("status") == "active",
    )


async def index_tenant_profile_for_rag(tenant: dict) -> None:
    tenant_id = tenant["_id"]
    content_parts = [
        tenant.get("name", ""),
        tenant.get("description", ""),
        f"City: {tenant.get('address', {}).get('city', '')}",
        f"Province: {tenant.get('address', {}).get('province', '')}",
        f"Contact phone: {tenant.get('contact', {}).get('phone', '')}",
        f"Contact email: {tenant.get('contact', {}).get('email', '')}",
        f"Website status: {tenant.get('websiteStatus', '')}",
        f"Language mode: {(tenant.get('settings') or {}).get('languageMode', '')}",
    ]
    website_settings = tenant.get("websiteSettings") or {}
    hero = website_settings.get("hero") or {}
    if hero.get("headline"):
        content_parts.append(f"Headline: {hero.get('headline')}")
    if hero.get("subheadline"):
        content_parts.append(f"Subheadline: {hero.get('subheadline')}")
    for faq in website_settings.get("faq", [])[:8]:
        question = faq.get("question", "")
        answer = faq.get("answer", "")
        if question or answer:
            content_parts.append(f"FAQ: {question} {answer}".strip())

    content = "\n".join(part for part in content_parts if part)
    await _upsert_knowledge_document(
        tenant_id=tenant_id,
        source_type="tenant_profile",
        source_id=tenant_id,
        module_code="website_builder",
        title=tenant.get("name", "Business Profile"),
        content=content,
        metadata={
            "slug": tenant.get("slug"),
            "websiteStatus": tenant.get("websiteStatus"),
            "status": tenant.get("status"),
        },
        is_active=tenant.get("status") == "active",
    )


async def reindex_tenant_knowledge(tenant_id: ObjectId) -> dict:
    return await rebuild_tenant_vector_index(tenant_id)


async def get_tenant_rag_status(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    knowledge_document_count = await db.knowledge_documents.count_documents({"tenantId": tenant_oid})
    active_knowledge_document_count = await db.knowledge_documents.count_documents({"tenantId": tenant_oid, "isActive": True})
    return {
        "tenant": serialize_document(tenant),
        "rag": {
            **(tenant.get("rag") or {}),
            "knowledgeDocumentCount": knowledge_document_count,
            "activeKnowledgeDocumentCount": active_knowledge_document_count,
            "collectionName": f"tenant_{tenant_oid}",
        },
    }


async def reindex_tenant_knowledge_for_owner(tenant_id: str, user: dict) -> dict:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    result = await reindex_tenant_knowledge(tenant_oid)
    status = await get_tenant_rag_status(tenant_id, user)
    status["rag"].update(result)
    return status
