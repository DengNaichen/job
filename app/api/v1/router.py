from fastapi import APIRouter

from app.api.v1 import jobs, sources

api_router = APIRouter()

api_router.include_router(jobs.router)
api_router.include_router(sources.router)
