import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")

engine = create_engine(
    _DATABASE_URL,
    connect_args={"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


from api.db import models as _models  # noqa: F401,E402


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
