import hashlib
import math
import re

import httpx

from app.core.config import settings

EMBEDDING_DIMENSION = 384


def _normalize_text(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _hashed_index(token: str, salt: str) -> tuple[int, int]:
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
    sign = 1 if digest[4] % 2 == 0 else -1
    return index, sign


def _token_features(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens = normalized.split()
    features = list(tokens)
    for token in tokens:
        if len(token) >= 5:
            features.append(token[:4])
            features.append(token[-4:])
        if len(token) >= 3:
            features.extend(token[index:index + 3] for index in range(len(token) - 2))
    return features


def generate_local_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for feature in _token_features(text):
        index, sign = _hashed_index(feature, "bizxus-rag")
        vector[index] += sign * 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


async def generate_embedding(text: str) -> tuple[list[float], str]:
    clean_text = str(text or "").strip()
    if not clean_text:
        return [0.0] * EMBEDDING_DIMENSION, "empty"

    if settings.openai_api_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.openai_embedding_model,
                        "input": clean_text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"], f"openai:{settings.openai_embedding_model}"
        except Exception:
            pass

    return generate_local_embedding(clean_text), "local-hash-v1"
