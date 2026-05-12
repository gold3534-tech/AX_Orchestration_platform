from pydantic import BaseModel


class TaskInputPresetResponse(BaseModel):
    id: str
    key: str
    label: str
    input_type: str
    description: str | None = None
    is_active: bool
    sort_order: int
