from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.orm import Session

from api.core.database import SessionLocal
from api.db.models import FlowRunEvent
from api.runtime.run_telemetry import redact_event_payload


SessionFactory = Callable[[], Session]


class FlowRunEventWriter:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        extra_redaction_values: Sequence[str] = (),
    ) -> None:
        self._session_factory = session_factory
        self._extra_redaction_values = tuple(extra_redaction_values)

    def add_event(
        self,
        *,
        run_id: str,
        node_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        db = self._session_factory()
        try:
            db.add(
                FlowRunEvent(
                    run_id=run_id,
                    node_id=node_id,
                    event_type=event_type,
                    event_payload_json=redact_event_payload(
                        payload,
                        extra_values=self._extra_redaction_values,
                    ),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
