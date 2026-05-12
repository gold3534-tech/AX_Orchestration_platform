from collections.abc import Generator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.core.database import Base, get_db
from api.db import models as _models  # noqa: F401
from api.dependencies import get_current_user
from api.main import app
from api.services.task_input_presets import ensure_task_input_presets_seeded

_TEST_USER = {"id": "test-user", "email": "test@example.com"}


def _create_legacy_delete_tables(session: Session) -> None:
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS asset_shares (
                asset_id TEXT
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS asset_imports (
                source_asset_id TEXT,
                imported_asset_id TEXT
            )
            """
        )
    )


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    ensure_task_input_presets_seeded(session)
    _create_legacy_delete_tables(session)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_current_user():
        return _TEST_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    @asynccontextmanager
    async def _test_lifespan(_app):
        yield

    try:
        with patch.object(app.router, "lifespan_context", _test_lifespan):
            with TestClient(app, raise_server_exceptions=False) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
