from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.db.models import FlowRun, FlowRunEvent


INTERRUPTED_RUN_MESSAGE = "Run interrupted before completion. Retry the run."
_INTERRUPTED_STATUSES = ("running", "executing")


def mark_stale_running_runs_failed(db: Session, *, older_than: datetime | None = None) -> int:
    cutoff = older_than or datetime.now(UTC)
    try:
        runs = (
            db.query(FlowRun)
            .filter(FlowRun.status.in_(_INTERRUPTED_STATUSES))
            .filter(FlowRun.updated_at < cutoff)
            .order_by(FlowRun.created_at.asc(), FlowRun.id.asc())
            .all()
        )
        if not runs:
            return 0

        finished_at = datetime.now(UTC)
        for run in runs:
            run.status = "failed"
            run.error_message = INTERRUPTED_RUN_MESSAGE
            run.finished_at = finished_at
            db.add(
                FlowRunEvent(
                    run_id=str(run.id),
                    node_id=None,
                    event_type="run_failed",
                    event_payload_json={
                        "type": "run_failed",
                        "run_id": str(run.id),
                        "node_id": None,
                        "error_message": INTERRUPTED_RUN_MESSAGE,
                        "error": INTERRUPTED_RUN_MESSAGE,
                        "interrupted": True,
                    },
                )
            )
            db.add(run)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return len(runs)
