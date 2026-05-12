from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.task_input_presets import TaskInputPresetResponse
from api.services.task_input_presets import list_task_input_presets as list_task_input_presets_service

router = APIRouter(prefix="/api/input-presets", tags=["input-presets"])


def _serialize_preset(row) -> TaskInputPresetResponse:
    return TaskInputPresetResponse(
        id=str(row.id),
        key=row.key,
        label=row.label,
        input_type=row.input_type,
        description=row.description,
        is_active=row.is_active,
        sort_order=row.sort_order,
    )


@router.get("", response_model=list[TaskInputPresetResponse])
def list_task_input_presets(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    rows = list_task_input_presets_service(db, include_inactive=include_inactive)
    return [_serialize_preset(row) for row in rows]
