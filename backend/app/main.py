from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import admin, auth, reader
from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import migrate_inferred_sermon_titles, migrate_legacy_user_login
from app.db.session import engine
from app.services.translation_recovery import recover_interrupted_translations


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    migrate_legacy_user_login(engine)
    migrate_inferred_sermon_titles(engine)
    Base.metadata.create_all(bind=engine)
    recover_interrupted_translations()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(reader.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
