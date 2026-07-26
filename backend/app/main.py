from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, SimpleRateLimitMiddleware
from app.db.indexes import create_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.db.seeders.seed_business_categories import seed_business_categories
from app.db.seeders.seed_admin import seed_default_admin
from app.db.seeders.seed_modules import seed_modules


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await connect_to_mongo()
    await create_indexes()
    await seed_default_admin()
    await seed_modules()
    await seed_business_categories()
    yield
    await close_mongo_connection()


def create_app() -> FastAPI:
    Path(settings.local_upload_dir).mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SimpleRateLimitMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/uploads", StaticFiles(directory=settings.local_upload_dir), name="uploads")
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
