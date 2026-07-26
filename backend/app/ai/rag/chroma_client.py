from pathlib import Path

import chromadb

from app.core.config import settings


class ChromaClient:
    def __init__(self) -> None:
        self._path = str(Path(settings.chroma_persist_directory).resolve())
        self._client = chromadb.PersistentClient(path=self._path)

    def get_or_create_collection(self, name: str):
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self, name: str) -> None:
        try:
            self._client.delete_collection(name)
        except Exception:
            return

    def status(self) -> dict[str, str | int | bool]:
        try:
            self._client.heartbeat()
            return {
                "configured": True,
                "connected": True,
                "mode": "persistent",
                "path": self._path,
                "host": settings.chroma_host,
                "port": settings.chroma_port,
            }
        except Exception as exc:
            return {
                "configured": True,
                "connected": False,
                "mode": "persistent",
                "path": self._path,
                "host": settings.chroma_host,
                "port": settings.chroma_port,
                "error": str(exc),
            }


chroma_client = ChromaClient()
