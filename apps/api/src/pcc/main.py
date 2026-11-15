import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pcc.api.api_tokens import router as api_tokens_router
from pcc.api.captures import router as captures_router
from pcc.api.chat import router as chat_router
from pcc.core.config import get_settings
from pcc.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_application: FastAPI):
    settings = get_settings()
    if settings.pcc_chat_assume_single_worker:
        from pcc.services.chat_recovery import recover_all_abandoned_running_runs

        # Must not block process bind / liveness when Postgres is unreachable
        # (smoke negatives and Render restarts). Readiness stays on /api/v1/ready.
        try:
            recovered = recover_all_abandoned_running_runs()
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            logger.warning(
                "Startup abandoned chat-run recovery skipped (database unavailable): %s",
                exc,
            )
        else:
            if recovered:
                logger.warning(
                    "Startup recovered %s abandoned chat run(s): %s",
                    len(recovered),
                    recovered,
                )
    else:
        logger.warning(
            "pcc_chat_assume_single_worker=false: abandoned chat-run recovery "
            "disabled; multi-worker cancel/recovery remains unsupported"
        )
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app using current settings (test-friendly)."""
    settings = get_settings()
    application = FastAPI(
        title="Personal Command Center API",
        version="0.1.0",
        docs_url="/docs" if settings.expose_api_docs else None,
        redoc_url="/redoc" if settings.expose_api_docs else None,
        openapi_url="/openapi.json" if settings.expose_api_docs else None,
        lifespan=_lifespan,
    )
    application.include_router(captures_router)
    application.include_router(api_tokens_router)
    application.include_router(chat_router)

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        """Liveness: process is up. Does not check dependencies."""
        return {"status": "ok", "service": "pcc-api"}

    @application.get("/api/v1/ready")
    def ready(response: Response) -> dict[str, str]:
        """Readiness: PostgreSQL is reachable. Unauthenticated (private network)."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError, TimeoutError):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "status": "unavailable",
                "service": "pcc-api",
                "database": "error",
            }
        return {"status": "ready", "service": "pcc-api", "database": "ok"}

    return application


app = create_app()
