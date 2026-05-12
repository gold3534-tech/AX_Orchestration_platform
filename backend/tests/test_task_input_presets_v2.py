from pathlib import Path

from sqlalchemy import UniqueConstraint

from api.db import models
from api.services.task_input_presets import ensure_task_input_presets_seeded


def test_preset_models_define_expected_tables_and_uniqueness():
    definition_constraints = [
        constraint
        for constraint in models.InputPresetDefinition.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    binding_constraints = [
        constraint
        for constraint in models.TaskInputPresetBinding.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert models.InputPresetDefinition.__tablename__ == "input_preset_definitions"
    assert models.TaskInputPresetBinding.__tablename__ == "task_input_preset_bindings"
    assert any([column.name for column in constraint.columns] == ["key"] for constraint in definition_constraints)
    assert any(
        [column.name for column in constraint.columns] == ["asset_version_id", "preset_id"]
        for constraint in binding_constraints
    )


def test_task_input_preset_sql_exists_for_postgres_schema_apply():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "002_task_input_presets.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()

    assert "CREATE TABLE IF NOT EXISTS input_preset_definitions" in sql
    assert "CREATE TABLE IF NOT EXISTS task_input_preset_bindings" in sql
    assert "asset_version_id UUID NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE" in sql
    assert "task_version_id UUID NOT NULL REFERENCES task_versions(version_id) ON DELETE CASCADE" not in sql
    assert "preset_id UUID NOT NULL REFERENCES input_preset_definitions(id) ON DELETE CASCADE" in sql


def test_get_input_presets_returns_seeded_active_catalog(client):
    response = client.get("/api/input-presets")

    assert response.status_code == 200
    assert [item["key"] for item in response.json()] == [
        "website_url",
        "keyword",
        "brand_name",
        "target_audience",
    ]
    assert response.json()[0]["label"] == "웹 사이트"
    assert response.json()[0]["input_type"] == "url"
    assert response.json()[0]["is_active"] is True


def test_seed_service_inserts_default_catalog_once(db):
    ensure_task_input_presets_seeded(db)
    ensure_task_input_presets_seeded(db)

    rows = db.query(models.InputPresetDefinition).order_by(models.InputPresetDefinition.sort_order.asc()).all()

    assert [row.key for row in rows] == [
        "website_url",
        "keyword",
        "brand_name",
        "target_audience",
    ]
    assert [row.sort_order for row in rows] == [1, 2, 3, 4]


def test_get_input_presets_hides_inactive_rows(client, db):
    response = client.get("/api/input-presets")
    first_id = response.json()[0]["id"]

    row = db.get(models.InputPresetDefinition, first_id)
    row.is_active = False
    db.commit()

    refreshed = client.get("/api/input-presets")

    assert refreshed.status_code == 200
    assert "website_url" not in [item["key"] for item in refreshed.json()]


def test_get_input_presets_orders_rows_by_sort_order(client, db):
    client.get("/api/input-presets")

    keyword_row = (
        db.query(models.InputPresetDefinition)
        .filter(models.InputPresetDefinition.key == "keyword")
        .one()
    )
    website_row = (
        db.query(models.InputPresetDefinition)
        .filter(models.InputPresetDefinition.key == "website_url")
        .one()
    )
    keyword_row.sort_order = 0
    website_row.sort_order = 5
    db.commit()

    response = client.get("/api/input-presets")

    assert response.status_code == 200
    assert [item["key"] for item in response.json()] == [
        "keyword",
        "brand_name",
        "target_audience",
        "website_url",
    ]


def test_get_input_presets_can_include_inactive_rows_for_admin_views(client, db):
    response = client.get("/api/input-presets")
    first_id = response.json()[0]["id"]

    row = db.get(models.InputPresetDefinition, first_id)
    row.is_active = False
    db.commit()

    refreshed = client.get("/api/input-presets?include_inactive=true")

    assert refreshed.status_code == 200
    by_key = {item["key"]: item for item in refreshed.json()}
    assert by_key["website_url"]["is_active"] is False


def test_list_input_presets_does_not_reseed_deleted_defaults(client, db):
    ensure_task_input_presets_seeded(db)
    target = (
        db.query(models.InputPresetDefinition)
        .filter(models.InputPresetDefinition.key == "target_audience")
        .one()
    )
    db.delete(target)
    db.commit()

    visible = client.get("/api/input-presets").json()

    assert "target_audience" not in [item["key"] for item in visible]


def test_list_input_presets_allows_empty_catalog_without_reseeding(client, db):
    ensure_task_input_presets_seeded(db)
    db.query(models.TaskInputPresetBinding).delete()
    db.query(models.InputPresetDefinition).delete()
    db.commit()

    visible = client.get("/api/input-presets")

    assert visible.status_code == 200
    assert visible.json() == []
