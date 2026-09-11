import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.private_uploads import ProtectedUploads

from app.api.v1.router import api_router
from app.core.config import settings, warn_about_insecure_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, SimpleRateLimitMiddleware
from app.db.indexes import create_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.db.seeders.seed_business_categories import seed_business_categories
from app.db.seeders.seed_admin import seed_default_admin
from app.db.seeders.seed_modules import seed_modules
from app.services.report_scheduler import report_scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    warn_about_insecure_settings()
    await connect_to_mongo()
    await create_indexes()
    await seed_default_admin()
    await seed_modules()
    await seed_business_categories()
    scheduler = asyncio.create_task(report_scheduler_loop()) if settings.report_scheduler_enabled else None
    try:
        yield
    finally:
        if scheduler:
            scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler
        await close_mongo_connection()


def create_app() -> FastAPI:
    Path(settings.local_upload_dir).mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title=settings.app_name,
        debug=False,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SimpleRateLimitMiddleware)

    # Any localhost port is convenient while developing (Vite moves ports when 5173 is
    # taken), but shipping a credentialed wildcard to production is not. Production
    # trusts only the configured allowlist.
    local_origin_regex = None if settings.app_env == "production" else r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=local_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/uploads", ProtectedUploads(directory=settings.local_upload_dir), name="uploads")
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
