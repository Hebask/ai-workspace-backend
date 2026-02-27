from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.repositories.chat_repo import ChatRepo
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.http_auth import router as auth_router
from app.api.ws import router as ws_router
from app.repositories.users_repo import UsersRepo
from app.repositories.files_repo import FilesRepo
import logging
from app.repositories.usage_repo import UsageRepo
from app.api.http_files import router as files_router
from app.api.http_images import router as images_router
from app.api.http_files_list import router as files_list_router
from app.api.http_images_list import router as images_list_router
from app.api.http_conversations import router as conversations_router
from app.api.http_usage import router as usage_router

app = FastAPI(title=settings.app_name)
logger = logging.getLogger("app")

setup_logging(settings.debug)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(files_router)
app.include_router(images_router)
app.include_router(files_list_router)
app.include_router(images_list_router)
app.include_router(conversations_router)
app.include_router(usage_router)

@app.on_event("startup")
async def on_startup():
    await UsersRepo.ensure_indexes()
    await ChatRepo.ensure_indexes()
    await FilesRepo.ensure_indexes()
    await UsageRepo.ensure_indexes()

@app.get("/health")
async def health():
    return {"ok": True, "env": settings.env}