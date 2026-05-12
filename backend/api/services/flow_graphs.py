from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion, Credential, FlowVersionDraft
from api.integrations.google_workspace import (
    GOOGLE_WORKSPACE_PROVIDER,
    google_workspace_runtime_context,
    resolve_google_sheets_runtime_token,
)
from api.runtime.credential_resolver import (
    CredentialResolutionError,
    collect_required_credential_providers,
    resolve_credential_env,
)
from api.runtime.credential_providers import provider_env_var, require_supported_provider
from api.runtime.env_overlay import runtime_env_overlay
from api.runtime.flow_diagnostics import run_compatibility_diagnostics, run_tool_mock_call_check
from api.runtime.loaders import FlowGraphLoader
from api.services.assets import (
    AssetConflictError,
    create_next_flow_draft_version,
    create_next_flow_version_with_snapshot,
    read_asset_with_current_version,
)
from api.services.llm_catalog import CatalogModel, load_llm_catalog_map

_FLOW_DRAFT_OWNER_UNIQUE_CONSTRAINT = "uq_flow_version_drafts_owner_asset"


def _read_owned_flow_asset(db: Session, *, flow_asset_id: str, owner_user_id: str):
    asset_read_model = read_asset_with_current_version(
        db,
        asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    if asset_read_model.asset.asset_type != "flow":
        raise ValueError(f"Asset is not a flow asset: {flow_asset_id}")
    return asset_read_model


def _is_flow_draft_owner_conflict(exc: IntegrityError) -> bool:
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == _FLOW_DRAFT_OWNER_UNIQUE_CONSTRAINT:
        return True

    message = str(orig).lower()
    return (
        _FLOW_DRAFT_OWNER_UNIQUE_CONSTRAINT in message
        or "unique constraint failed: flow_version_drafts.flow_asset_id, flow_version_drafts.owner_user_id" in message
        or (
            "duplicate key value violates unique constraint" in message
            and _FLOW_DRAFT_OWNER_UNIQUE_CONSTRAINT in message
        )
    )


def _get_or_create_draft(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> FlowVersionDraft:
    asset_read_model = _read_owned_flow_asset(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    draft = (
        db.query(FlowVersionDraft)
        .filter(
            FlowVersionDraft.flow_asset_id == flow_asset_id,
            FlowVersionDraft.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
    current_version_id = str(asset_read_model.current_version.id)
    if draft is not None:
        if draft.base_version_id is None or str(draft.base_version_id) != current_version_id:
            draft.base_version_id = current_version_id
        return draft

    return FlowVersionDraft(
        flow_asset_id=asset_read_model.asset.id,
        base_version_id=asset_read_model.current_version.id,
        owner_user_id=owner_user_id,
        graph_json={},
        validation_json={},
        last_test_validation_json={},
    )


def _ensure_editable_flow_base_version(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> AssetVersion:
    asset_read_model = _read_owned_flow_asset(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    if asset_read_model.current_version.status == "published":
        created = create_next_flow_draft_version(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
            base_version_id=str(asset_read_model.current_version.id),
            commit=False,
        )
        return created["asset_version"]
    return asset_read_model.current_version


def get_flow_draft(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> FlowVersionDraft:
    _read_owned_flow_asset(db, flow_asset_id=flow_asset_id, owner_user_id=owner_user_id)
    draft = (
        db.query(FlowVersionDraft)
        .filter(
            FlowVersionDraft.flow_asset_id == flow_asset_id,
            FlowVersionDraft.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
    if draft is None:
        raise LookupError(f"Flow draft not found: {flow_asset_id}")
    return draft


def _commit_and_refresh_draft(db: Session, draft: FlowVersionDraft) -> FlowVersionDraft:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(draft)
    return draft


def save_flow_draft(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
    graph: dict[str, Any],
) -> FlowVersionDraft:
    try:
        editable_base_version = _ensure_editable_flow_base_version(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
        )
        draft = _get_or_create_draft(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
        )
        draft.base_version_id = editable_base_version.id
        draft.graph_json = graph
        draft.validation_json = {}
        draft.last_test_validation_json = {}
        db.add(draft)
        return _commit_and_refresh_draft(db, draft)
    except IntegrityError as exc:
        if not _is_flow_draft_owner_conflict(exc):
            db.rollback()
            raise
    except Exception:
        db.rollback()
        raise

    try:
        editable_base_version = _ensure_editable_flow_base_version(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
        )
        draft = get_flow_draft(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
        )
        draft.base_version_id = editable_base_version.id
        draft.graph_json = graph
        draft.validation_json = {}
        draft.last_test_validation_json = {}
        db.add(draft)
        return _commit_and_refresh_draft(db, draft)
    except Exception:
        db.rollback()
        raise


def _published_crew_lookup(db: Session, *, owner_user_id: str):
    def lookup(*, asset_id: str, version_id: str) -> dict[str, Any] | None:
        row = (
            db.query(AssetVersion.asset_id, AssetVersion.id, AssetRuntimeSnapshot.runtime_snapshot_json)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .outerjoin(AssetRuntimeSnapshot, AssetRuntimeSnapshot.version_id == AssetVersion.id)
            .filter(
                AssetVersion.id == version_id,
                AssetVersion.asset_id == asset_id,
                Asset.owner_user_id == owner_user_id,
                Asset.asset_type == "crew",
                AssetVersion.status.in_(("published", "archived")),
            )
            .one_or_none()
        )
        if row is None:
            return None

        latest = (
            db.query(AssetVersion.id)
            .filter(
                AssetVersion.asset_id == asset_id,
                AssetVersion.status == "published",
            )
            .order_by(AssetVersion.version_number.desc(), AssetVersion.created_at.desc(), AssetVersion.id.desc())
            .first()
        )
        return {
            "asset_id": str(row.asset_id),
            "version_id": str(row.id),
            "latest_version_id": str(latest[0]) if latest else str(row.id),
            "runtime_snapshot_json": row.runtime_snapshot_json or {},
        }

    return lookup


def validate_flow_draft(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    draft = get_flow_draft(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    snapshot = FlowGraphLoader().validate(
        draft.graph_json,
        published_crew_lookup=_published_crew_lookup(db, owner_user_id=owner_user_id),
    )
    draft.last_test_validation_json = snapshot
    db.add(draft)
    _commit_and_refresh_draft(db, draft)
    return snapshot


def _snapshot_with_runtime_crew_snapshots(
    db: Session,
    *,
    snapshot: dict[str, Any],
    owner_user_id: str,
) -> dict[str, Any]:
    enriched = dict(snapshot)
    crew_snapshots: dict[str, dict[str, Any]] = {}
    crew_refs = snapshot.get("crew_refs")
    if not isinstance(crew_refs, list):
        enriched["crew_snapshots"] = crew_snapshots
        return enriched

    for ref in crew_refs:
        if not isinstance(ref, dict):
            continue
        node_id = ref.get("node_id")
        version_id = ref.get("version_id")
        asset_id = ref.get("asset_id")
        if not all(isinstance(value, str) and value.strip() for value in (node_id, version_id, asset_id)):
            continue
        row = (
            db.query(AssetRuntimeSnapshot.runtime_snapshot_json)
            .select_from(AssetRuntimeSnapshot)
            .join(AssetVersion, AssetVersion.id == AssetRuntimeSnapshot.version_id)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .filter(
                AssetRuntimeSnapshot.version_id == version_id,
                AssetVersion.status.in_(("published", "archived")),
                Asset.asset_type == "crew",
                Asset.owner_user_id == owner_user_id,
                Asset.id == asset_id,
            )
            .one_or_none()
        )
        if row is not None and isinstance(row.runtime_snapshot_json, dict):
            crew_snapshots[node_id] = row.runtime_snapshot_json
    enriched["crew_snapshots"] = crew_snapshots
    return enriched


def _flow_snapshot_for_diagnostics(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    draft = get_flow_draft(db, flow_asset_id=flow_asset_id, owner_user_id=owner_user_id)
    snapshot = FlowGraphLoader().validate(
        draft.graph_json,
        published_crew_lookup=_published_crew_lookup(db, owner_user_id=owner_user_id),
    )
    return _snapshot_with_runtime_crew_snapshots(
        db,
        snapshot=snapshot,
        owner_user_id=owner_user_id,
    )


def run_flow_compatibility_diagnostics(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _flow_snapshot_for_diagnostics(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    llm_catalog = load_llm_catalog_map(db)
    credential_env, _available_credential_providers = _diagnostic_credential_env_for_snapshot(
        db,
        snapshot=snapshot,
        owner_user_id=owner_user_id,
        llm_catalog=llm_catalog,
    )
    redaction_values = {value for value in credential_env.values() if value != _MISSING_CREDENTIAL_ENV_VALUE}
    with (
        runtime_env_overlay(credential_env),
        google_workspace_runtime_context(db=db, owner_user_id=owner_user_id),
    ):
        return run_compatibility_diagnostics(
            snapshot=snapshot,
            inputs=inputs,
            redaction_values=redaction_values,
            llm_catalog=llm_catalog,
        )


_MISSING_CREDENTIAL_ENV_VALUE = "__AI_OH_MISSING_CREDENTIAL__"


def _required_credential_providers_for_snapshot(
    snapshot: dict[str, Any],
    *,
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> list[str]:
    providers: set[str] = set()
    crew_snapshots = snapshot.get("crew_snapshots")
    if isinstance(crew_snapshots, dict):
        for crew_snapshot in crew_snapshots.values():
            if isinstance(crew_snapshot, dict):
                providers.update(
                    collect_required_credential_providers(
                        crew_snapshot=crew_snapshot,
                        llm_catalog=llm_catalog,
                    )
                )
    return sorted(providers)


def _string_set(value: object) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    if isinstance(value, list):
        return {item.strip() for item in value if isinstance(item, str) and item.strip()}
    return set()


def _linked_tool_payloads_for_snapshot(snapshot: dict[str, Any]) -> list[Mapping[str, Any]]:
    payloads: list[Mapping[str, Any]] = []
    crew_snapshots = snapshot.get("crew_snapshots")
    if not isinstance(crew_snapshots, Mapping):
        return payloads
    for crew_snapshot in crew_snapshots.values():
        if not isinstance(crew_snapshot, Mapping):
            continue
        runtime_crew = crew_snapshot.get("runtime_crew")
        runtime_crew = runtime_crew if isinstance(runtime_crew, Mapping) else {}
        agent_ids = _string_set(runtime_crew.get("agent_version_ids"))
        manager_agent_id = runtime_crew.get("manager_agent_version_id")
        if isinstance(manager_agent_id, str) and manager_agent_id.strip():
            agent_ids.add(manager_agent_id.strip())
        task_ids = _string_set(runtime_crew.get("task_version_ids"))
        task_agent_links = crew_snapshot.get("task_agent_links")
        if isinstance(task_agent_links, Mapping):
            for task_id in task_ids:
                agent_id = task_agent_links.get(task_id)
                if isinstance(agent_id, str) and agent_id.strip():
                    agent_ids.add(agent_id.strip())
        tool_keys: set[str] = set()
        agent_tool_links = crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links")
        if isinstance(agent_tool_links, Mapping):
            for agent_id in agent_ids:
                tool_keys.update(_string_set(agent_tool_links.get(agent_id)))
        task_tool_links = crew_snapshot.get("task_tool_links")
        if isinstance(task_tool_links, Mapping):
            for task_id in task_ids:
                tool_keys.update(_string_set(task_tool_links.get(task_id)))
        runtime_tools = crew_snapshot.get("runtime_tools")
        if not isinstance(runtime_tools, Mapping):
            continue
        for tool_key in tool_keys:
            tool_payload = runtime_tools.get(tool_key)
            if isinstance(tool_payload, Mapping):
                payloads.append(tool_payload)
    return payloads


def _tool_env_isolation_requirements(
    snapshot: dict[str, Any],
    *,
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> tuple[set[str], set[str]]:
    providers = set(_required_credential_providers_for_snapshot(snapshot, llm_catalog=llm_catalog))
    env_names: set[str] = set()
    for tool_payload in _linked_tool_payloads_for_snapshot(snapshot):
        credential_requirements = tool_payload.get("credential_requirements")
        if isinstance(credential_requirements, list):
            for requirement in credential_requirements:
                if not isinstance(requirement, Mapping):
                    continue
                injection = requirement.get("injection")
                if isinstance(injection, str) and injection.strip() and injection.strip() != "env":
                    continue
                provider = requirement.get("provider")
                if isinstance(provider, str) and provider.strip():
                    providers.add(provider.strip())
                env_var = requirement.get("env_var")
                if isinstance(env_var, str) and env_var.strip():
                    env_names.add(env_var.strip())
        required_env_vars = tool_payload.get("required_env_vars")
        if isinstance(required_env_vars, list):
            for requirement in required_env_vars:
                if not isinstance(requirement, Mapping):
                    continue
                name = requirement.get("name")
                if isinstance(name, str) and name.strip():
                    env_names.add(name.strip())
    return providers, env_names


def _runtime_context_credential_providers_for_snapshot(snapshot: dict[str, Any]) -> set[str]:
    providers: set[str] = set()
    for tool_payload in _linked_tool_payloads_for_snapshot(snapshot):
        credential_requirements = tool_payload.get("credential_requirements")
        if not isinstance(credential_requirements, list):
            continue
        for requirement in credential_requirements:
            if not isinstance(requirement, Mapping):
                continue
            if requirement.get("required") is not True:
                continue
            if requirement.get("injection") != "runtime_context":
                continue
            provider = requirement.get("provider")
            if isinstance(provider, str) and provider.strip():
                providers.add(provider.strip())
    return providers


def _has_active_runtime_context_credential(
    db: Session,
    *,
    owner_user_id: str,
    provider: str,
) -> bool:
    if provider == GOOGLE_WORKSPACE_PROVIDER:
        try:
            resolve_google_sheets_runtime_token(
                db,
                owner_user_id=owner_user_id,
            )
        except CredentialResolutionError:
            return False
        return True

    try:
        provider_metadata = require_supported_provider(provider)
    except ValueError:
        return False
    if provider_metadata.auth_type != "oauth2":
        return False
    return (
        db.query(Credential)
        .filter(
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.provider == provider_metadata.provider,
            Credential.auth_type == provider_metadata.auth_type,
            Credential.status == "active",
        )
        .first()
        is not None
    )


def _diagnostic_credential_env_for_snapshot(
    db: Session,
    *,
    snapshot: dict[str, Any],
    owner_user_id: str,
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> tuple[dict[str, str], list[str]]:
    credential_env: dict[str, str] = {}
    available_providers: list[str] = []
    providers, env_names = _tool_env_isolation_requirements(snapshot, llm_catalog=llm_catalog)
    for provider in sorted(providers):
        try:
            provider_env = resolve_credential_env(
                db,
                owner_user_id=owner_user_id,
                providers=[provider],
            )
        except CredentialResolutionError:
            try:
                credential_env[provider_env_var(provider)] = _MISSING_CREDENTIAL_ENV_VALUE
            except ValueError:
                pass
            continue
        credential_env.update(provider_env)
        available_providers.append(provider)
    for provider in sorted(_runtime_context_credential_providers_for_snapshot(snapshot)):
        if _has_active_runtime_context_credential(
            db,
            owner_user_id=owner_user_id,
            provider=provider,
        ):
            available_providers.append(provider)
    for env_name in sorted(env_names):
        credential_env.setdefault(env_name, _MISSING_CREDENTIAL_ENV_VALUE)
    return credential_env, sorted(set(available_providers))


def run_flow_tool_mock_call_diagnostics(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    snapshot = _flow_snapshot_for_diagnostics(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    llm_catalog = load_llm_catalog_map(db)
    credential_env, available_credential_providers = _diagnostic_credential_env_for_snapshot(
        db,
        snapshot=snapshot,
        owner_user_id=owner_user_id,
        llm_catalog=llm_catalog,
    )
    redaction_values = {value for value in credential_env.values() if value != _MISSING_CREDENTIAL_ENV_VALUE}
    redaction_values.add(_MISSING_CREDENTIAL_ENV_VALUE)
    with (
        runtime_env_overlay(credential_env),
        google_workspace_runtime_context(db=db, owner_user_id=owner_user_id),
    ):
        return run_tool_mock_call_check(
            snapshot=snapshot,
            live_credential_providers=available_credential_providers,
            redaction_values=redaction_values,
        )


def publish_flow_draft(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    draft = get_flow_draft(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    snapshot = FlowGraphLoader().validate(
        draft.graph_json,
        published_crew_lookup=_published_crew_lookup(db, owner_user_id=owner_user_id),
    )
    draft.validation_json = snapshot
    draft.last_test_validation_json = snapshot

    asset_read_model = _read_owned_flow_asset(
        db,
        flow_asset_id=flow_asset_id,
        owner_user_id=owner_user_id,
    )
    current_version_id = str(asset_read_model.current_version.id)
    if draft.base_version_id is None:
        draft.base_version_id = current_version_id
    elif str(draft.base_version_id) != current_version_id:
        db.rollback()
        raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.")

    db.add(draft)

    try:
        published = create_next_flow_version_with_snapshot(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=owner_user_id,
            runtime_snapshot_json=snapshot,
            base_version_id=str(draft.base_version_id) if draft.base_version_id is not None else None,
            commit=False,
        )
        draft.base_version_id = published["asset_version"].id
        db.add(draft)
        db.commit()
    except (AssetConflictError, IntegrityError, LookupError, ValueError):
        db.rollback()
        raise

    db.refresh(draft)
    db.refresh(published["asset"])
    db.refresh(published["asset_version"])
    db.refresh(published["runtime_snapshot"])
    published["already_published"] = False
    return published


def list_published_crews_for_flow_builder(db: Session, *, owner_user_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(
            Asset.id.label("asset_id"),
            Asset.name,
            Asset.description,
            AssetVersion.id.label("version_id"),
            AssetVersion.version_number,
            AssetVersion.status,
            AssetRuntimeSnapshot.runtime_snapshot_json,
        )
        .join(AssetVersion, AssetVersion.asset_id == Asset.id)
        .outerjoin(AssetRuntimeSnapshot, AssetRuntimeSnapshot.version_id == AssetVersion.id)
        .filter(
            Asset.owner_user_id == owner_user_id,
            Asset.asset_type == "crew",
            AssetVersion.status == "published",
        )
        .order_by(
            Asset.name.asc(),
            AssetVersion.version_number.desc(),
            AssetVersion.created_at.desc(),
            AssetVersion.id.desc(),
        )
        .all()
    )
    crews: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    for row in rows:
        asset_id = str(row.asset_id)
        if asset_id in seen_asset_ids:
            continue
        if not isinstance(row.runtime_snapshot_json, dict) or not row.runtime_snapshot_json:
            continue
        seen_asset_ids.add(asset_id)
        crews.append(
            {
                "asset_id": asset_id,
                "version_id": str(row.version_id),
                "version_no": row.version_number,
                "name": row.name,
                "description": row.description,
                "status": row.status,
                "runtime_snapshot_json": row.runtime_snapshot_json or {},
            }
        )
    return crews


def _snapshot_has_input_node(snapshot: dict[str, Any]) -> bool:
    graph = snapshot.get("graph") if isinstance(snapshot, dict) else None
    if not isinstance(graph, dict):
        return False
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return False
    return any(isinstance(node, dict) and node.get("type") == "input" for node in nodes)


def list_published_flows_for_run_page(db: Session, *, owner_user_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(
            Asset.id.label("asset_id"),
            Asset.name,
            Asset.description,
            AssetVersion.id.label("version_id"),
            AssetVersion.version_number,
            AssetVersion.status,
            AssetRuntimeSnapshot.runtime_snapshot_json,
        )
        .join(AssetVersion, AssetVersion.asset_id == Asset.id)
        .join(AssetRuntimeSnapshot, AssetRuntimeSnapshot.version_id == AssetVersion.id)
        .filter(
            Asset.owner_user_id == owner_user_id,
            Asset.asset_type == "flow",
            AssetVersion.status == "published",
        )
        .order_by(
            Asset.name.asc(),
            AssetVersion.version_number.desc(),
            AssetVersion.created_at.desc(),
            AssetVersion.id.desc(),
        )
        .all()
    )
    flows: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    for row in rows:
        asset_id = str(row.asset_id)
        if asset_id in seen_asset_ids:
            continue
        snapshot = row.runtime_snapshot_json or {}
        if not isinstance(snapshot, dict) or not snapshot:
            continue
        seen_asset_ids.add(asset_id)
        flows.append(
            {
                "asset_id": asset_id,
                "version_id": str(row.version_id),
                "version_no": row.version_number,
                "name": row.name,
                "description": row.description,
                "status": row.status,
                "has_input_node": _snapshot_has_input_node(snapshot),
            }
        )
    return flows
