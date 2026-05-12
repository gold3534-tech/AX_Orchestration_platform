from sqlalchemy.orm import Session

from api.db.models import Asset, AssetVersion, InputPresetDefinition, TaskInputPresetBinding

DEFAULT_TASK_INPUT_PRESETS = [
    {
        "key": "website_url",
        "label": "웹 사이트",
        "input_type": "url",
        "description": "분석할 웹사이트 주소",
        "sort_order": 1,
    },
    {
        "key": "keyword",
        "label": "검색어",
        "input_type": "text",
        "description": "분석할 핵심 검색어",
        "sort_order": 2,
    },
    {
        "key": "brand_name",
        "label": "브랜드명",
        "input_type": "text",
        "description": "문서에 반영할 브랜드 이름",
        "sort_order": 3,
    },
    {
        "key": "target_audience",
        "label": "타겟 독자",
        "input_type": "text",
        "description": "콘텐츠를 읽는 대상 독자",
        "sort_order": 4,
    },
]


def ensure_task_input_presets_seeded(db: Session) -> None:
    existing = {
        row.key
        for row in db.query(InputPresetDefinition.key).filter(
            InputPresetDefinition.key.in_([item["key"] for item in DEFAULT_TASK_INPUT_PRESETS])
        )
    }
    missing_rows = [
        InputPresetDefinition(is_active=True, **item)
        for item in DEFAULT_TASK_INPUT_PRESETS
        if item["key"] not in existing
    ]
    if missing_rows:
        db.add_all(missing_rows)
        db.flush()


def list_task_input_presets(db: Session, *, include_inactive: bool = False) -> list[InputPresetDefinition]:
    query = db.query(InputPresetDefinition)
    if not include_inactive:
        query = query.filter(InputPresetDefinition.is_active.is_(True))
    return query.order_by(InputPresetDefinition.sort_order.asc(), InputPresetDefinition.created_at.asc()).all()


def list_active_task_input_presets(db: Session) -> list[InputPresetDefinition]:
    return list_task_input_presets(db, include_inactive=False)


def normalize_task_input_preset_keys(preset_keys: list[str]) -> list[str]:
    return list(dict.fromkeys(preset_keys))


def resolve_active_task_input_presets(db: Session, preset_keys: list[str]) -> list[InputPresetDefinition]:
    unique_keys = normalize_task_input_preset_keys(preset_keys)
    if not unique_keys:
        return []

    rows = (
        db.query(InputPresetDefinition)
        .filter(
            InputPresetDefinition.key.in_(unique_keys),
            InputPresetDefinition.is_active.is_(True),
        )
        .all()
    )
    rows_by_key = {row.key: row for row in rows}
    missing = [key for key in unique_keys if key not in rows_by_key]
    if missing:
        raise ValueError(f"Unknown or inactive task input preset keys: {', '.join(missing)}")
    return [rows_by_key[key] for key in unique_keys]


def replace_task_input_preset_bindings(db: Session, *, asset_version_id: str, preset_keys: list[str]) -> None:
    asset_type = (
        db.query(Asset.asset_type)
        .join(AssetVersion, AssetVersion.asset_id == Asset.id)
        .filter(AssetVersion.id == asset_version_id)
        .scalar()
    )
    if asset_type != "task":
        raise ValueError(f"Asset version is not a task version: {asset_version_id}")

    preset_rows = resolve_active_task_input_presets(db, preset_keys)
    db.query(TaskInputPresetBinding).filter(TaskInputPresetBinding.asset_version_id == asset_version_id).delete()
    db.flush()
    db.add_all(
        [
            TaskInputPresetBinding(
                asset_version_id=asset_version_id,
                preset_id=row.id,
                sort_order=index + 1,
                is_required=False,
            )
            for index, row in enumerate(preset_rows)
        ]
    )
    db.flush()


def list_task_input_preset_keys_by_version_ids(db: Session, version_ids: list[str]) -> dict[str, list[str]]:
    if not version_ids:
        return {}

    rows = (
        db.query(TaskInputPresetBinding)
        .join(InputPresetDefinition, InputPresetDefinition.id == TaskInputPresetBinding.preset_id)
        .filter(TaskInputPresetBinding.asset_version_id.in_(version_ids))
        .order_by(
            TaskInputPresetBinding.asset_version_id.asc(),
            TaskInputPresetBinding.sort_order.asc(),
            TaskInputPresetBinding.created_at.asc(),
            TaskInputPresetBinding.id.asc(),
        )
        .all()
    )

    grouped: dict[str, list[str]] = {str(version_id): [] for version_id in version_ids}
    for row in rows:
        grouped.setdefault(str(row.asset_version_id), []).append(row.preset_definition.key)
    return grouped
