import math
import re
from datetime import datetime, timezone

from bson import ObjectId

from app.ai.rag.chroma_client import chroma_client
from app.core.object_ids import serialize_document
from app.db.mongodb import get_database
from app.services.rag_embedding_service import generate_embedding

CHUNK_SIZE = 420
CHUNK_OVERLAP = 80


def _collection_name(tenant_id: ObjectId) -> str:
    return f"tenant_{tenant_id}"


def chunk_text(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return []
    if len(clean) <= CHUNK_SIZE:
        return [clean]

    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + CHUNK_SIZE)
        chunk = clean[start:end]
        if end < len(clean):
            split = max(chunk.rfind(". "), chunk.rfind("; "), chunk.rfind(", "), chunk.rfind(" "))
            if split > CHUNK_OVERLAP:
                end = start + split + 1
                chunk = clean[start:end]
        chunks.append(chunk.strip())
        if end >= len(clean):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [chunk for chunk in chunks if chunk]


async def upsert_knowledge_document_vectors(document: dict) -> dict:
    tenant_id = document["tenantId"]
    collection = chroma_client.get_or_create_collection(_collection_name(tenant_id))
    content = document.get("content", "")
    chunks = chunk_text(content)

    if not document.get("isActive", True) or not chunks:
        delete_knowledge_document_vectors(document)
        return {"chunkCount": 0, "embeddingProvider": "none"}

    embeddings = []
    ids = []
    metadatas = []
    documents = []
    provider = "local-hash-v1"

    for index, chunk in enumerate(chunks):
        embedding, provider = await generate_embedding(chunk)
        ids.append(f"{document['chromaDocumentId']}::chunk::{index}")
        documents.append(chunk)
        embeddings.append(embedding)
        metadatas.append(
            {
                "tenantId": str(tenant_id),
                "knowledgeDocumentId": str(document["_id"]),
                "sourceType": str(document.get("sourceType", "")),
                "title": str(document.get("title", "")),
                "moduleCode": str(document.get("moduleCode", "")),
                "tags": ", ".join(str(tag) for tag in document.get("tags", [])[:12]),
                "chunkIndex": index,
                "isActive": bool(document.get("isActive", True)),
                "createdAt": document.get("createdAt", datetime.now(timezone.utc)).isoformat(),
                "updatedAt": document.get("updatedAt", datetime.now(timezone.utc)).isoformat(),
            }
        )

    collection.delete(where={"knowledgeDocumentId": str(document["_id"])})
    collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    return {"chunkCount": len(chunks), "embeddingProvider": provider}


def delete_knowledge_document_vectors(document: dict) -> None:
    collection = chroma_client.get_or_create_collection(_collection_name(document["tenantId"]))
    collection.delete(where={"knowledgeDocumentId": str(document["_id"])})


async def rebuild_tenant_vector_index(tenant_id: ObjectId) -> dict:
    db = get_database()
    cursor = db.knowledge_documents.find({"tenantId": tenant_id})
    total = 0
    active = 0
    total_chunks = 0
    provider = "none"

    async for document in cursor:
        total += 1
        if document.get("isActive", True):
            active += 1
        result = await upsert_knowledge_document_vectors(document)
        total_chunks += result["chunkCount"]
        provider = result["embeddingProvider"]

    await db.tenants.update_one(
        {"_id": tenant_id},
        {
            "$set": {
                "rag.lastIndexedAt": datetime.now(timezone.utc),
                "rag.knowledgeDocumentCount": total,
                "rag.activeKnowledgeDocumentCount": active,
                "rag.chunkCount": total_chunks,
                "rag.embeddingProvider": provider,
                "rag.indexStatus": "ready",
            }
        },
    )
    return {
        "knowledgeDocumentCount": total,
        "activeKnowledgeDocumentCount": active,
        "chunkCount": total_chunks,
        "embeddingProvider": provider,
    }


def _keyword_score(query_tokens: set[str], source_text: str) -> float:
    if not query_tokens:
        return 0.0
    source_tokens = set(re.findall(r"[a-z0-9]+", source_text.lower()))
    if not source_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(source_tokens))
    coverage = overlap / max(len(query_tokens), 1)
    density = overlap / max(len(source_tokens), 1)
    return min(1.0, coverage * 0.82 + density * 0.18)


def _vector_confidence(distance: float | int | None) -> float:
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance)))


async def hybrid_retrieve_knowledge(tenant: dict, query_text: str, limit: int = 5) -> list[dict]:
    db = get_database()
    tenant_id = tenant["_id"]
    collection = chroma_client.get_or_create_collection(_collection_name(tenant_id))
    query_embedding, _ = await generate_embedding(query_text)
    vector_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(limit * 2, 6),
        where={"isActive": True},
        include=["documents", "metadatas", "distances"],
    )

    query_tokens = set(re.findall(r"[a-z0-9]+", query_text.lower()))
    merged: dict[str, dict] = {}
    ids = (vector_results.get("metadatas") or [[]])[0]
    docs = (vector_results.get("documents") or [[]])[0]
    distances = (vector_results.get("distances") or [[]])[0]

    for metadata, excerpt, distance in zip(ids, docs, distances, strict=False):
        knowledge_id = metadata.get("knowledgeDocumentId")
        if not knowledge_id:
            continue
        vector_confidence = round(_vector_confidence(distance), 4)
        keyword_confidence = round(_keyword_score(query_tokens, excerpt), 4)
        existing = merged.get(knowledge_id)
        row = {
            "knowledgeDocumentId": knowledge_id,
            "title": metadata.get("title", ""),
            "sourceType": metadata.get("sourceType", ""),
            "excerpt": excerpt,
            "chunkIndex": metadata.get("chunkIndex", 0),
            "vectorConfidence": vector_confidence,
            "keywordConfidence": keyword_confidence,
            "matchType": "vector",
        }
        if not existing or (vector_confidence + keyword_confidence) > (existing["vectorConfidence"] + existing["keywordConfidence"]):
            merged[knowledge_id] = row

    lexical_query = {
        "tenantId": tenant_id,
        "isActive": True,
        "$or": (
            [{"content": {"$regex": token, "$options": "i"}} for token in list(query_tokens)[:8]]
            + [{"title": {"$regex": token, "$options": "i"}} for token in list(query_tokens)[:8]]
        )
        if query_tokens
        else [],
    }
    lexical_cursor = db.knowledge_documents.find(lexical_query if lexical_query["$or"] else {"tenantId": tenant_id, "isActive": True}).sort("updatedAt", -1).limit(limit * 2)
    async for document in lexical_cursor:
        serialized = serialize_document(document)
        knowledge_id = serialized["id"]
        content = serialized.get("content", "") or ""
        chunks = chunk_text(content) or [content[:420]]
        best_chunk = max(chunks, key=lambda chunk: _keyword_score(query_tokens, f"{serialized.get('title', '')} {chunk}"))
        lexical_score = round(_keyword_score(query_tokens, f"{serialized.get('title', '')} {' '.join(serialized.get('tags') or [])} {best_chunk}"), 4)
        if knowledge_id in merged:
            merged[knowledge_id]["keywordConfidence"] = max(merged[knowledge_id]["keywordConfidence"], lexical_score)
            if lexical_score > _keyword_score(query_tokens, merged[knowledge_id].get("excerpt", "")):
                merged[knowledge_id]["excerpt"] = best_chunk[:520]
            merged[knowledge_id]["matchType"] = "hybrid"
        else:
            merged[knowledge_id] = {
                "knowledgeDocumentId": knowledge_id,
                "title": serialized.get("title", ""),
                "sourceType": serialized.get("sourceType", ""),
                "excerpt": best_chunk[:520],
                "chunkIndex": 0,
                "vectorConfidence": 0.0,
                "keywordConfidence": lexical_score,
                "matchType": "keyword",
            }

    knowledge_ids = [ObjectId(key) for key in merged.keys()]
    knowledge_map = {
        str(document["_id"]): serialize_document(document)
        async for document in db.knowledge_documents.find({"_id": {"$in": knowledge_ids}})
    } if knowledge_ids else {}

    ranked = []
    for key, row in merged.items():
        document = knowledge_map.get(key)
        if not document:
            continue
        final_confidence = round(
            min(
                1.0,
                max(row["vectorConfidence"], row["keywordConfidence"]) * 0.72
                + min(row["vectorConfidence"], row["keywordConfidence"]) * 0.28
                + (0.08 if row["matchType"] == "hybrid" else 0),
            ),
            4,
        )
        ranked.append(
            {
                **document,
                "excerpt": row["excerpt"],
                "chunkIndex": row.get("chunkIndex", 0),
                "matchType": row["matchType"],
                "vectorConfidence": row["vectorConfidence"],
                "keywordConfidence": row["keywordConfidence"],
                "confidence": final_confidence,
            }
        )

    ranked.sort(key=lambda item: (item["confidence"], item.get("updatedAt", "")), reverse=True)
    return ranked[:limit]
