from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import admin, auth, live, owner, reader
from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import (
    migrate_inferred_sermon_titles,
    migrate_legacy_user_login,
    migrate_super_admin,
    migrate_translation_languages,
)
from app.db.session import engine
from app.services.translation_recovery import recover_interrupted_translations


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    migrate_legacy_user_login(engine)
    migrate_inferred_sermon_titles(engine)
    migrate_translation_languages(engine)
    migrate_super_admin(engine)
    Base.metadata.create_all(bind=engine)
    recover_interrupted_translations()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(reader.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(owner.router, prefix=settings.api_prefix)
app.include_router(live.router, prefix=settings.api_prefix)


@app.middleware("http")
async def no_live_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if "/live" in path or path.endswith("live-worker-token"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def audit_owner_sermon_changes(request, call_next):
    response = await call_next(request)
    # All owner writes through the existing review/upload endpoints are also recorded.
    if (
        request.method != "GET"
        and response.status_code < 400
        and request.url.path.startswith(settings.api_prefix + "/admin/")
        and not request.url.path.endswith("/live/audio")
    ):
        import jwt

        from app.core.security import decode_access_token
        from app.db.session import SessionLocal
        from app.models import User, UserRole
        from app.models.entities import AdminAudit

        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            try:
                payload = decode_access_token(authorization[7:])
                with SessionLocal() as db:
                    actor = db.get(User, payload.get("sub"))
                    if actor and actor.role == UserRole.SUPER_ADMIN:
                        db.add(
                            AdminAudit(
                                actor_id=actor.id,
                                action=request.method,
                                target_id=request.url.path,
                                details="Khutba workspace operation",
                            )
                        )
                        db.commit()
            except jwt.PyJWTError:
                pass
    return response


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
