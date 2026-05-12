from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError

load_dotenv()

from .routes.auth import router as auth_router
from .routes.assets import router as assets_router
from .routes.capabilities import router as capabilities_router
from .routes.connected_accounts import router as connected_accounts_router
from .routes.crew_graphs import router as crew_graphs_router
from .routes.flow_graphs import router as flow_graphs_router
from .routes.knowledge import router as knowledge_router
from .routes.llm_catalog import router as llm_catalog_router
from .routes.task_input_presets import router as task_input_presets_router
from .routes.runs import router as runs_router
from .routes.runtime import router as runtime_router
from .routes.tooling import router as tooling_router
from .dependencies import get_current_user
from .core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    recovery_cutoff = datetime.now(UTC)
    Base.metadata.create_all(bind=engine)
    from .core.database import SessionLocal
    from .services.run_recovery import mark_stale_running_runs_failed

    db = SessionLocal()
    try:
        mark_stale_running_runs_failed(db, older_than=recovery_cutoff)
    finally:
        db.close()

    # Warm up Supabase client on startup
    from .supabase_client import get_supabase
    get_supabase()
    yield


app = FastAPI(title="CrewAI Platform API", lifespan=lifespan)
logger = logging.getLogger(__name__)

def _parse_cors_origins(cors_origins_env: str | None) -> list[str]:
    if cors_origins_env is None:
        return ["http://localhost:3000"]
    return [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]


cors_origins = _parse_cors_origins(os.environ.get("CORS_ORIGINS"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth")
protected_router_dependencies = [Depends(get_current_user)]

app.include_router(assets_router, dependencies=protected_router_dependencies)
app.include_router(capabilities_router, dependencies=protected_router_dependencies)
app.include_router(connected_accounts_router)
app.include_router(crew_graphs_router, dependencies=protected_router_dependencies)
app.include_router(flow_graphs_router, dependencies=protected_router_dependencies)
app.include_router(knowledge_router, dependencies=protected_router_dependencies)
app.include_router(task_input_presets_router, dependencies=protected_router_dependencies)
app.include_router(runs_router)
app.include_router(runtime_router, dependencies=protected_router_dependencies)
app.include_router(tooling_router, dependencies=protected_router_dependencies)
app.include_router(llm_catalog_router, dependencies=protected_router_dependencies)


def _is_schema_or_system_db_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return any(
        keyword in message
        for keyword in (
            "does not exist",
            "undefinedtable",
            "undefinedcolumn",
            "no such table",
            "no such column",
        )
    )


@app.exception_handler(ProgrammingError)
async def handle_programming_error(_request: Request, exc: ProgrammingError):
    logger.exception("Database programming error", exc_info=exc)
    if _is_schema_or_system_db_error(exc):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "시스템 점검 중입니다. 잠시 후 다시 시도해주세요."},
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "유효하지 않은 요청입니다."},
    )


@app.exception_handler(OperationalError)
async def handle_operational_error(_request: Request, exc: OperationalError):
    logger.exception("Database operational error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "시스템 점검 중입니다. 잠시 후 다시 시도해주세요."},
    )


@app.exception_handler(DataError)
async def handle_data_error(_request: Request, exc: DataError):
    logger.exception("Database data error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "유효하지 않은 요청입니다."},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
