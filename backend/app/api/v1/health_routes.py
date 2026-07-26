from fastapi import APIRouter

from app.ai.rag.chroma_client import chroma_client
from app.core.config import settings
from app.db.mongodb import get_mongo_status
from app.services.system_validation_service import build_demo_accounts, build_readiness_report
from app.services.qa_service import build_phase_summary
from app.services.submission_service import build_public_submission_summary

router = APIRouter()


@router.get("/health")
async def health_check():
    mongo = await get_mongo_status()
    return {
        "success": True,
        "message": "BizxusAI API is running.",
        "data": {
            "service": settings.app_name,
            "environment": settings.app_env,
            "mongodb": mongo,
            "chroma": chroma_client.status(),
        },
        "meta": {},
    }


@router.get("/health/readiness")
async def readiness_check():
    report = await build_readiness_report()
    return {
        "success": report["overallStatus"] != "not_ready",
        "message": "Deployment readiness report generated successfully.",
        "data": report,
        "meta": {},
    }


@router.get("/health/demo-accounts")
async def demo_accounts():
    return {
        "success": True,
        "message": "Demo account information fetched successfully.",
        "data": build_demo_accounts(),
        "meta": {},
    }


@router.get("/health/phase-summary")
async def phase_summary():
    return {
        "success": True,
        "message": "Phase implementation summary fetched successfully.",
        "data": build_phase_summary(),
        "meta": {},
    }


@router.get("/health/submission-summary")
async def submission_summary():
    return {
        "success": True,
        "message": "Submission summary fetched successfully.",
        "data": build_public_submission_summary(),
        "meta": {},
    }
