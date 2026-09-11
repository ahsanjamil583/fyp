"""Replace a public signing key without displaying it or changing integration keys."""
import secrets
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings

if __name__ == "__main__":
    env = Path(__file__).resolve().parents[1] / ".env"
    if settings.jwt_secret_is_public:
        set_key(str(env), "JWT_SECRET_KEY", secrets.token_urlsafe(48))
        print("Replaced the public signing key. Existing sessions require a fresh login after restart.")
    else:
        print("Signing key already private; unchanged.")
    set_key(str(env), "DEBUG", "false")
    bridge_url = dotenv_values(env).get("WHATSAPP_BRIDGE_PUBLIC_URL") or ""
    if not bridge_url or urlsplit(bridge_url).hostname in {"localhost", "127.0.0.1"}:
        set_key(str(env), "WHATSAPP_BRIDGE_PUBLIC_URL", "/whatsapp-bridge")
    frontend = env.parent.parent / "frontend"
    for name in (".env", ".env.local", ".env.development", ".env.development.local", ".env.production", ".env.production.local"):
        target = frontend / name
        if target.exists():
            url = dotenv_values(target).get("VITE_API_BASE_URL") or ""
            if not url or urlsplit(url).hostname in {"localhost", "127.0.0.1"}:
                set_key(str(target), "VITE_API_BASE_URL", "/api/v1")
    print("Public debug tracebacks disabled. Integration credentials unchanged.")
    print("Local frontend API and bridge links use the frontend proxy.")
