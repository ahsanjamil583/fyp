import logging
import threading
from pathlib import Path

import chromadb

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChromaClient:
    """Lazily-opened persistent Chroma client.

    The underlying store is opened on first use rather than at import time. Opening it
    during import made module import order significant, meant a corrupt store crashed
    the process before logging was configured, and gave every forked uvicorn worker its
    own writer against the same SQLite file.
    """

    def __init__(self) -> None:
        self._path = str(Path(settings.chroma_persist_directory).resolve())
        self._client = None
        self._lock = threading.Lock()

    @property
    def path(self) -> str:
        return self._path

    def _get_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    Path(self._path).mkdir(parents=True, exist_ok=True)
                    self._client = chromadb.PersistentClient(path=self._path)
                    logger.info("Opened Chroma persistent store at %s", self._path)
        return self._client

    def get_or_create_collection(self, name: str):
        return self._get_client().get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self, name: str) -> None:
        try:
            self._get_client().delete_collection(name)
        except Exception as exc:
            logger.warning("Could not delete Chroma collection %s: %s", name, exc)

    def close(self) -> None:
        self._client = None

    def status(self) -> dict[str, str | int | bool]:
        base = {
            "configured": True,
            "mode": "persistent",
            "path": self._path,
            "host": settings.chroma_host,
            "port": settings.chroma_port,
        }
        try:
            self._get_client().heartbeat()
            return {**base, "connected": True}
        except Exception as exc:
            logger.warning("Chroma store is not reachable: %s", exc)
            return {**base, "connected": False, "error": str(exc)}


chroma_client = ChromaClient()
