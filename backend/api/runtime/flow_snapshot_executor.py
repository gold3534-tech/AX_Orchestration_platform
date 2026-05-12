from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import (
    Asset,
    AssetRuntimeSnapshot,
    AssetVersion,
    FlowRun,
    FlowRunEvent,
    FlowRunStateSnapshot,
    HumanFeedbackRequest,
)
from api.integrations.google_workspace import (
    google_workspace_runtime_context,
    resolve_google_drive_runtime_token,
    resolve_google_sheets_runtime_token_for_crew,
    runtime_oauth_redaction_values,
)
from api.integrations.meta_instagram import (
    meta_instagram_runtime_context,
    resolve_meta_instagram_runtime_token_for_crew,
)
from api.runtime.credential_resolver import (
    CredentialResolutionError,
    collect_required_credential_providers,
    resolve_credential_env,
)
from api.runtime.crewai_event_bridge import crewai_event_bridge
from api.runtime.crewai_factory import CrewAIFactory
from api.runtime.env_overlay import runtime_env_overlay
from api.runtime.event_writer import FlowRunEventWriter
from api.runtime.execution_actions import ExecutionActionRequest, execute_execution_action
from api.runtime.hitl_policy import (
    HITL_MESSAGE,
    VALID_HITL_OUTCOMES,
    retry_budget_metadata,
)
from api.runtime.linear_flow_runtime import (
    UnsupportedGraphError,
    build_crew_inputs,
    build_linear_path,
    build_output_payload,
    normalize_crew_output,
    read_path,
)
from api.runtime.node_output_store import NodeOutputStore
from api.runtime.run_telemetry import FlowRunEventSink, redact_event_payload, redact_secret_text
from api.services.llm_catalog import load_llm_catalog_map
from api.tools.nano_banana_image_tool import nano_banana_artifact_runtime_context


class FlowRuntimeSnapshotError(ValueError):
    pass


class HumanFeedbackConflictError(ValueError):
    pass


class HumanFeedbackValidationError(ValueError):
    pass


class _TransactionBoundSemanticEventWriter:
    def __init__(
        self,
        *,
        executor: "FlowSnapshotExecutor",
        extra_redaction_values: tuple[str, ...],
    ) -> None:
        self._executor = executor
        self._extra_redaction_values = set(extra_redaction_values)

    def add_event(
        self,
        *,
        run_id: str,
        node_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self._executor._add_event(
            run_id=run_id,
            node_id=node_id,
            event_type=event_type,
            payload=payload,
            extra_redaction_values=self._extra_redaction_values,
        )


class FlowSnapshotExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def load_published_snapshot(
        self,
        *,
        flow_version_id: str,
        owner_user_id: str,
    ) -> dict[str, Any]:
        row = (
            self._db.query(AssetRuntimeSnapshot.runtime_snapshot_json)
            .select_from(AssetVersion)
            .outerjoin(AssetRuntimeSnapshot, AssetRuntimeSnapshot.version_id == AssetVersion.id)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .filter(
                AssetVersion.id == flow_version_id,
                AssetVersion.status == "published",
                Asset.asset_type == "flow",
                Asset.owner_user_id == owner_user_id,
            )
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"Published flow version not found: {flow_version_id}")

        snapshot = row.runtime_snapshot_json
        if not isinstance(snapshot, dict) or not snapshot:
            raise FlowRuntimeSnapshotError("Published flow version is missing runtime_snapshot_json.")
        if "schemaVersion" not in snapshot:
            raise FlowRuntimeSnapshotError("Published flow runtime snapshot is missing schemaVersion.")
        return snapshot

    def start_run(
        self,
        *,
        flow_version_id: str,
        owner_user_id: str,
        inputs: dict[str, Any],
        capture_agent_execution_logs: bool = True,
    ) -> FlowRun:
        snapshot = self.load_published_snapshot(
            flow_version_id=flow_version_id,
            owner_user_id=owner_user_id,
        )
        run: FlowRun | None = None
        try:
            run = FlowRun(
                flow_version_id=flow_version_id,
                status="running",
                input_json=inputs,
                started_at=datetime.now(UTC),
            )
            self._db.add(run)
            self._db.flush()
            state = {
                "inputs": inputs,
                "state": dict(inputs),
                "node_outputs": {},
                "node_output_refs": {},
                "node_output_versions": {},
                "transfer_values": {},
                "human_feedback": {},
                "human_feedback_history": [],
                "run_options": {"capture_agent_execution_logs": capture_agent_execution_logs},
                # include published flow entities (crews, agents) so the frontend can render known agents
                "published_snapshot_entities": snapshot.get("entities", {}),
            }
            self._add_state_snapshot(run_id=str(run.id), node_id=None, state=state)
            self._add_event(
                run_id=str(run.id),
                node_id=None,
                event_type="run_started",
                payload={"flow_version_id": flow_version_id},
            )

            return self._execute_run_path(
                run=run,
                snapshot=snapshot,
                state=state,
                owner_user_id=owner_user_id,
                capture_agent_execution_logs=capture_agent_execution_logs,
                use_immediate_event_writer=False,
            )
        except Exception:
            run_id = str(run.id) if run is not None and run.id is not None else None
            self._db.rollback()
            if run_id is not None:
                self._db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id).delete(
                    synchronize_session=False
                )
                self._db.query(FlowRunStateSnapshot).filter(FlowRunStateSnapshot.run_id == run_id).delete(
                    synchronize_session=False
                )
                self._db.query(FlowRun).filter(FlowRun.id == run_id).delete(synchronize_session=False)
                self._db.commit()
            raise

    def create_run_record(
        self,
        *,
        flow_version_id: str,
        owner_user_id: str,
        inputs: dict[str, Any],
        capture_agent_execution_logs: bool = True,
    ) -> FlowRun:
        snapshot = self.load_published_snapshot(
            flow_version_id=flow_version_id,
            owner_user_id=owner_user_id,
        )
        try:
            run = FlowRun(
                flow_version_id=flow_version_id,
                status="running",
                input_json=inputs,
                started_at=datetime.now(UTC),
            )
            self._db.add(run)
            self._db.flush()
            state = {
                "inputs": inputs,
                "state": dict(inputs),
                "node_outputs": {},
                "node_output_refs": {},
                "node_output_versions": {},
                "transfer_values": {},
                "human_feedback": {},
                "human_feedback_history": [],
                "run_options": {"capture_agent_execution_logs": capture_agent_execution_logs},
                # include published flow entities (crews, agents) so the frontend can render known agents
                "published_snapshot_entities": snapshot.get("entities", {}),
            }
            self._add_state_snapshot(run_id=str(run.id), node_id=None, state=state)
            self._add_event(
                run_id=str(run.id),
                node_id=None,
                event_type="run_started",
                payload={"type": "run_started", "flow_version_id": flow_version_id},
            )
            self._db.add(run)
            self._db.commit()
            self._db.refresh(run)
            return run
        except Exception:
            self._db.rollback()
            raise

    def execute_existing_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
    ) -> FlowRun:
        run = self._owned_run(run_id=run_id, owner_user_id=owner_user_id)
        if run.status != "running":
            return run

        claimed_count = (
            self._db.query(FlowRun)
            .filter(FlowRun.id == run_id, FlowRun.status == "running")
            .update({FlowRun.status: "executing"}, synchronize_session=False)
        )
        if claimed_count != 1:
            self._db.rollback()
            return self._owned_run(run_id=run_id, owner_user_id=owner_user_id)
        self._db.commit()

        run = self._owned_run(run_id=run_id, owner_user_id=owner_user_id)

        snapshot = self.load_published_snapshot(
            flow_version_id=str(run.flow_version_id),
            owner_user_id=owner_user_id,
        )
        latest_snapshot = self._latest_state_snapshot(run_id=str(run.id))
        state = latest_snapshot.state_json if latest_snapshot is not None else {
            "inputs": run.input_json or {},
            "state": dict(run.input_json or {}),
            "node_outputs": {},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": True},
        }
        capture_agent_execution_logs = bool(
            (state.get("run_options") or {}).get("capture_agent_execution_logs", True)
        )
        return self._execute_run_path(
            run=run,
            snapshot=snapshot,
            state=state,
            owner_user_id=owner_user_id,
            capture_agent_execution_logs=capture_agent_execution_logs,
            use_immediate_event_writer=True,
        )

    def _latest_state_snapshot(self, *, run_id: str) -> FlowRunStateSnapshot | None:
        return (
            self._db.query(FlowRunStateSnapshot)
            .filter(FlowRunStateSnapshot.run_id == run_id)
            .order_by(FlowRunStateSnapshot.created_at.desc(), FlowRunStateSnapshot.id.desc())
            .first()
        )

    def _execute_run_path(
        self,
        *,
        run: FlowRun,
        snapshot: dict[str, Any],
        state: dict[str, Any],
        owner_user_id: str,
        capture_agent_execution_logs: bool,
        use_immediate_event_writer: bool = True,
    ) -> FlowRun:
        llm_catalog = load_llm_catalog_map(self._db)
        redaction_values: set[str] = set()
        failure_redaction_values: set[str] = set()
        active_node_id: str | None = None
        active_node_type: str | None = None
        try:
            path = build_linear_path(snapshot)
            for node in path:
                node_type = node.get("type")
                node_id = str(node.get("id"))
                active_node_id = node_id
                active_node_type = str(node_type) if node_type is not None else None
                if node_type == "output":
                    output = build_output_payload(
                        snapshot=snapshot,
                        state=state["state"],
                        node_outputs=state["node_outputs"],
                    )
                    output = self._redact_runtime_value(output, extra_redaction_values=redaction_values)
                    state["output"] = output
                    run.output_json = output
                    run.status = "completed"
                    run.finished_at = datetime.now(UTC)
                    self._add_state_snapshot(
                        run_id=str(run.id),
                        node_id=node_id,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="run_completed",
                        payload={"output": output},
                        extra_redaction_values=redaction_values,
                    )
                    break
                if node_type == "hitl":
                    self._pause_for_human(
                        run=run,
                        snapshot=snapshot,
                        node=node,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    break
                if node_type == "execution_action":
                    drive_token = self._google_drive_token_for_execution_action(
                        node=node,
                        owner_user_id=owner_user_id,
                        approved=False,
                    )
                    oauth_redaction_values = runtime_oauth_redaction_values(drive_token)
                    redaction_values.update(oauth_redaction_values)
                    failure_redaction_values.update(oauth_redaction_values)
                    action_context = (
                        google_workspace_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            drive_token=drive_token,
                        )
                        if drive_token is not None
                        else nullcontext()
                    )
                    with action_context:
                        action_result = self._execute_execution_action_node(
                            run=run,
                            node=node,
                            state=state,
                            owner_user_id=owner_user_id,
                            extra_redaction_values=redaction_values,
                        )
                    if action_result.status == "pending_approval":
                        break
                    continue
                if node_type == "crew":
                    crew_snapshot = self._crew_runtime_snapshot_for_node(
                        snapshot=snapshot,
                        crew_node=node,
                        owner_user_id=owner_user_id,
                    )
                    crew_inputs = build_crew_inputs(
                        snapshot=snapshot,
                        crew_node_id=node_id,
                        state=state["state"],
                        node_outputs=state["node_outputs"],
                    )
                    callback_redaction_values = set(redaction_values)
                    callback_redaction_values.update(self._crew_input_redaction_values(crew_inputs))
                    failure_redaction_values.update(callback_redaction_values)
                    for input_name, input_value in crew_inputs.items():
                        if isinstance(input_value, str):
                            state["transfer_values"][f"{node_id}.{input_name}"] = {
                                "type": "text",
                                "length": len(input_value),
                            }
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="crew_started",
                        payload={"inputs": self._redact_crew_inputs_for_event(crew_inputs)},
                    )
                    instrumentation_callbacks = self._instrumentation_callbacks_for_node(
                        run_id=str(run.id),
                        node_id=node_id,
                        capture_agent_execution_logs=capture_agent_execution_logs,
                        extra_redaction_values=callback_redaction_values,
                    )
                    required_providers = collect_required_credential_providers(
                        crew_snapshot=crew_snapshot,
                        llm_catalog=llm_catalog,
                    )
                    credential_env = resolve_credential_env(
                        self._db,
                        owner_user_id=owner_user_id,
                        providers=required_providers,
                    )
                    redaction_values.update(value for value in credential_env.values() if value)
                    callback_redaction_values.update(value for value in credential_env.values() if value)
                    failure_redaction_values.update(value for value in credential_env.values() if value)
                    sheets_token = resolve_google_sheets_runtime_token_for_crew(
                        self._db,
                        owner_user_id=owner_user_id,
                        crew_snapshot=crew_snapshot,
                    )
                    instagram_token = resolve_meta_instagram_runtime_token_for_crew(
                        self._db,
                        owner_user_id=owner_user_id,
                        crew_snapshot=crew_snapshot,
                    )
                    oauth_redaction_values = runtime_oauth_redaction_values(sheets_token, instagram_token)
                    redaction_values.update(oauth_redaction_values)
                    callback_redaction_values.update(oauth_redaction_values)
                    failure_redaction_values.update(oauth_redaction_values)
                    event_writer = self._semantic_event_writer(
                        extra_redaction_values=tuple(callback_redaction_values),
                        use_immediate_event_writer=use_immediate_event_writer,
                    )
                    with (
                        runtime_env_overlay(credential_env),
                        google_workspace_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            sheets_token=sheets_token,
                        ),
                        meta_instagram_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            run_id=str(run.id),
                            token=instagram_token,
                        ),
                        nano_banana_artifact_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            run_id=str(run.id),
                            node_id=node_id,
                        ),
                    ):
                        crew = CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog, db=self._db).build_crew(
                            runtime_crew=crew_snapshot.get("runtime_crew", {}),
                            runtime_agents=crew_snapshot.get("runtime_agents", {}),
                            runtime_tasks=crew_snapshot.get("runtime_tasks", {}),
                            task_agent_links=crew_snapshot.get("task_agent_links", {}),
                            agent_tool_links=self._agent_tool_links_for_crew_snapshot(crew_snapshot),
                            task_tool_links=crew_snapshot.get("task_tool_links", {}),
                            runtime_tools=crew_snapshot.get("runtime_tools", {}),
                            agent_knowledge_links=crew_snapshot.get("agent_knowledge_links", {}),
                            runtime_knowledge=crew_snapshot.get("runtime_knowledge", {}),
                            instrumentation_callbacks=instrumentation_callbacks,
                        )
                        with crewai_event_bridge(
                            writer=event_writer,
                            run_id=str(run.id),
                            node_id=node_id,
                        ):
                            crew_output = self._redact_runtime_value(
                                normalize_crew_output(crew.kickoff(inputs=crew_inputs)),
                                extra_redaction_values=redaction_values,
                            )
                    NodeOutputStore(self._db).store_output(
                        run_id=str(run.id),
                        node_id=node_id,
                        output=crew_output,
                        state=state,
                    )
                    self._add_state_snapshot(
                        run_id=str(run.id),
                        node_id=node_id,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="crew_completed",
                        payload={"output": crew_output},
                        extra_redaction_values=redaction_values,
                    )
                    continue
                raise UnsupportedGraphError(f"Unsupported flow runtime node type: {node_type}")
        except (UnsupportedGraphError, HumanFeedbackValidationError, CredentialResolutionError):
            self._db.rollback()
            raise
        except Exception as exc:
            run_id = str(run.id)
            flow_version_id = run.flow_version_id
            input_json = deepcopy(run.input_json) if isinstance(run.input_json, dict) else {}
            redacted_error = redact_secret_text(str(exc), extra_values=tuple(redaction_values))
            redacted_error = redact_secret_text(redacted_error, extra_values=tuple(failure_redaction_values))
            self._db.rollback()
            persisted_run = self._db.get(FlowRun, run_id)
            if persisted_run is None:
                persisted_run = FlowRun(
                    id=run_id,
                    flow_version_id=flow_version_id,
                    status="running",
                    input_json=input_json,
                )
                self._db.add(persisted_run)
            run = persisted_run
            run.status = "failed"
            run.error_message = redacted_error
            run.finished_at = datetime.now(UTC)
            if active_node_type == "crew" and active_node_id is not None:
                self._add_event(
                    run_id=str(run.id),
                    node_id=active_node_id,
                    event_type="crew_failed",
                    payload={
                        "type": "crew_failed",
                        "run_id": str(run.id),
                        "node_id": active_node_id,
                        "error_message": redacted_error,
                        "fatal": True,
                    },
                    extra_redaction_values=failure_redaction_values,
                )
            self._add_event(
                run_id=str(run.id),
                node_id=active_node_id,
                event_type="run_failed",
                payload={
                    "type": "run_failed",
                    "run_id": str(run.id),
                    "node_id": active_node_id,
                    "error_message": redacted_error,
                    "error": redacted_error,
                },
                extra_redaction_values=failure_redaction_values,
            )

        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        return run

    def resume_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
        request_id: str,
        outcome: str,
        feedback: str,
        idempotency_key: str | None = None,
    ) -> FlowRun:
        if outcome not in VALID_HITL_OUTCOMES:
            raise HumanFeedbackValidationError("outcome must be one of approved, needs_revision, rejected")

        run = self._owned_run(run_id=run_id, owner_user_id=owner_user_id)
        request = (
            self._db.query(HumanFeedbackRequest)
            .filter(HumanFeedbackRequest.id == request_id, HumanFeedbackRequest.run_id == run.id)
            .one_or_none()
        )
        if request is None:
            raise LookupError(f"Human feedback request not found: {request_id}")

        try:
            if request.status != "pending":
                raise HumanFeedbackConflictError("Human feedback request has already been resolved.")
            if outcome == "needs_revision":
                remaining_retries = int((request.prompt_json or {}).get("remaining_retries") or 0)
                if remaining_retries <= 0:
                    raise HumanFeedbackValidationError(
                        "Retry budget has been exhausted for this HITL request."
                    )
            llm_catalog = load_llm_catalog_map(self._db) if outcome in {"approved", "needs_revision"} else None
            feedback_result = self._feedback_result(request=request, outcome=outcome, feedback=feedback)
            responded_at = datetime.now(UTC)
            try:
                updated_count = (
                    self._db.query(HumanFeedbackRequest)
                    .filter(
                        HumanFeedbackRequest.id == request_id,
                        HumanFeedbackRequest.run_id == run.id,
                        HumanFeedbackRequest.status == "pending",
                    )
                    .update(
                        {
                            HumanFeedbackRequest.status: "resolved",
                            HumanFeedbackRequest.response_json: feedback_result,
                            HumanFeedbackRequest.responded_at: responded_at,
                            HumanFeedbackRequest.resolved_by: owner_user_id,
                            HumanFeedbackRequest.idempotency_key: idempotency_key,
                        },
                        synchronize_session=False,
                    )
                )
            except IntegrityError as exc:
                self._db.rollback()
                raise HumanFeedbackConflictError(
                    "Human feedback idempotency key has already been used for this run."
                ) from exc
            if updated_count != 1:
                raise HumanFeedbackConflictError("Human feedback request has already been resolved.")

            self._db.refresh(request)
            self._add_event(
                run_id=str(run.id),
                node_id=request.node_id,
                event_type="hitl_resolved",
                payload={
                    "type": "hitl_resolved",
                    "run_id": str(run.id),
                    "node_id": request.node_id,
                    "request_id": str(request.id),
                    "outcome": outcome,
                    "feedback": feedback,
                },
            )

            if outcome == "rejected":
                run.status = "rejected"
                run.finished_at = datetime.now(UTC)
                self._add_event(
                    run_id=str(run.id),
                    node_id=request.node_id,
                    event_type="run_rejected",
                    payload={
                        "type": "run_rejected",
                        "run_id": str(run.id),
                        "node_id": request.node_id,
                        "request_id": str(request.id),
                        "feedback": feedback,
                    },
                )
                self._db.add(run)
                self._db.commit()
                self._db.refresh(run)
                return run

            if outcome == "approved":
                snapshot = self.load_published_snapshot(
                    flow_version_id=str(run.flow_version_id),
                    owner_user_id=owner_user_id,
                )
                state = self._latest_state(run_id=str(run.id))
                approved_execution_action_node_ids: set[str] = set()
                if self._is_execution_action_approval(request):
                    start_index = self._path_index_for_node(snapshot=snapshot, node_id=request.node_id)
                    runtime_context_by_node = {}
                    approved_execution_action_node_ids.add(request.node_id)
                else:
                    self._store_feedback_in_state(state=state, request=request, feedback_result=feedback_result)
                    start_index = int(
                        (request.prompt_json or {}).get("resume_path_index")
                        or self._path_index_after_node(snapshot=snapshot, node_id=request.node_id)
                    )
                    runtime_context_by_node = self._runtime_context_for_downstream(
                        snapshot=snapshot,
                        start_index=start_index,
                        request=request,
                        feedback_result=feedback_result,
                    )
                run.status = "running"
                self._execute_from_path_index(
                    run=run,
                    snapshot=snapshot,
                    path_index=start_index,
                    owner_user_id=owner_user_id,
                    state=state,
                    runtime_context_by_node=runtime_context_by_node,
                    llm_catalog=llm_catalog,
                    approved_execution_action_node_ids=approved_execution_action_node_ids,
                )
                self._db.add(run)
                self._db.commit()
                self._db.refresh(run)
                return run

            self._retry_previous_crew(
                run=run,
                request=request,
                feedback_result=feedback_result,
                llm_catalog=llm_catalog,
            )
            self._db.add(run)
            self._db.commit()
            self._db.refresh(run)
            return run
        except Exception:
            self._db.rollback()
            raise

    def _add_event(
        self,
        *,
        run_id: str,
        node_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        extra_redaction_values: set[str] | None = None,
    ) -> None:
        self._db.add(
            FlowRunEvent(
                run_id=run_id,
                node_id=node_id,
                event_type=event_type,
                event_payload_json=redact_event_payload(
                    payload,
                    extra_values=tuple(extra_redaction_values or ()),
                ),
            )
        )

    def _event_writer(self, *, extra_redaction_values: tuple[str, ...]) -> FlowRunEventWriter:
        session_factory = sessionmaker(bind=self._db.get_bind(), autocommit=False, autoflush=False)
        return FlowRunEventWriter(
            session_factory=session_factory,
            extra_redaction_values=extra_redaction_values,
        )

    def _semantic_event_writer(
        self,
        *,
        extra_redaction_values: tuple[str, ...],
        use_immediate_event_writer: bool,
    ) -> Any:
        if use_immediate_event_writer:
            return self._event_writer(extra_redaction_values=extra_redaction_values)
        return _TransactionBoundSemanticEventWriter(
            executor=self,
            extra_redaction_values=extra_redaction_values,
        )

    def _redact_crew_inputs_for_event(self, inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
        redacted: dict[str, dict[str, Any]] = {}
        for key, value in inputs.items():
            if isinstance(value, str):
                redacted[key] = {"type": "text", "length": len(value)}
            elif isinstance(value, list):
                redacted[key] = {"type": "array", "length": len(value)}
            elif isinstance(value, dict):
                redacted[key] = {
                    "type": "object",
                    "keys": sorted(str(item_key) for item_key in value.keys()),
                }
            elif value is None:
                redacted[key] = {"type": "null"}
            else:
                redacted[key] = {"type": type(value).__name__}
        return redacted

    def _add_state_snapshot(
        self,
        *,
        run_id: str,
        node_id: str | None,
        state: dict[str, Any],
        extra_redaction_values: set[str] | None = None,
    ) -> None:
        self._db.add(
            FlowRunStateSnapshot(
                run_id=run_id,
                node_id=node_id,
                state_json=redact_event_payload(
                    deepcopy(state),
                    extra_values=tuple(extra_redaction_values or ()),
                ),
            )
        )

    def _instrumentation_callbacks_for_node(
        self,
        *,
        run_id: str,
        node_id: str,
        capture_agent_execution_logs: bool,
        extra_redaction_values: set[str] | None = None,
    ) -> dict[str, object] | None:
        if not capture_agent_execution_logs:
            return None
        return FlowRunEventSink(
            self._db,
            run_id=run_id,
            node_id=node_id,
            extra_redaction_values=extra_redaction_values if extra_redaction_values is not None else (),
        ).callback_bundle()

    def _crew_input_redaction_values(self, inputs: dict[str, Any]) -> set[str]:
        values: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, str):
                values.add(value)
                return
            if isinstance(value, dict):
                for item in value.values():
                    collect(item)
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)

        for value in inputs.values():
            collect(value)
        return {value for value in values if len(value) >= 4}

    def _crew_runtime_snapshot_for_node(
        self,
        *,
        snapshot: dict[str, Any],
        crew_node: dict[str, Any],
        owner_user_id: str,
    ) -> dict[str, Any]:
        return self._db_crew_runtime_snapshot_for_node(
            snapshot=snapshot,
            crew_node=crew_node,
            owner_user_id=owner_user_id,
        )

    def _db_crew_runtime_snapshot_for_node(
        self,
        *,
        snapshot: dict[str, Any],
        crew_node: dict[str, Any],
        owner_user_id: str,
    ) -> dict[str, Any]:
        node_id = str(crew_node.get("id") or "")
        node_data = crew_node.get("data")
        if not isinstance(node_data, dict):
            raise UnsupportedGraphError(f"Crew node {crew_node.get('id')} is missing versionId.")
        version_id = str(node_data.get("versionId") or "")
        if not version_id:
            raise UnsupportedGraphError(f"Crew node {crew_node.get('id')} is missing versionId.")
        node_asset_id = node_data.get("assetId")
        if node_asset_id is not None and (not isinstance(node_asset_id, str) or not node_asset_id.strip()):
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")

        crew_refs = snapshot.get("crew_refs")
        if not isinstance(crew_refs, list):
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
        matching_ref = next(
            (
                ref
                for ref in crew_refs
                if isinstance(ref, dict)
                and str(ref.get("node_id") or "") == node_id
                and str(ref.get("version_id") or "") == version_id
            ),
            None,
        )
        if matching_ref is None:
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
        ref_asset_id = matching_ref.get("asset_id")
        if not isinstance(ref_asset_id, str) or not ref_asset_id.strip():
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
        if isinstance(node_asset_id, str) and node_asset_id.strip() and node_asset_id != ref_asset_id:
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")

        row = (
            self._db.query(AssetRuntimeSnapshot.runtime_snapshot_json)
            .select_from(AssetRuntimeSnapshot)
            .join(AssetVersion, AssetVersion.id == AssetRuntimeSnapshot.version_id)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .filter(
                AssetRuntimeSnapshot.version_id == version_id,
                AssetVersion.status.in_(("published", "archived")),
                Asset.asset_type == "crew",
                Asset.owner_user_id == owner_user_id,
                Asset.id == ref_asset_id,
            )
            .one_or_none()
        )
        if row is None or not isinstance(row.runtime_snapshot_json, dict) or not row.runtime_snapshot_json:
            raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
        return row.runtime_snapshot_json

    def _execute_execution_action_node(
        self,
        *,
        run: FlowRun,
        node: dict[str, Any],
        state: dict[str, Any],
        owner_user_id: str,
        extra_redaction_values: set[str] | None = None,
        approved: bool = False,
    ):
        node_id = str(node.get("id") or "")
        node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
        action_key = str(node_data.get("action_key") or node_data.get("actionKey") or "")
        if not action_key:
            raise UnsupportedGraphError(f"Execution Action node {node_id} is missing action_key.")

        action_inputs = self._execution_action_inputs(
            node_id=node_id,
            node_data=node_data,
            state=state,
        )
        action_result = execute_execution_action(
            self._db,
            ExecutionActionRequest(
                run_id=str(run.id),
                node_id=node_id,
                action_key=action_key,
                owner_user_id=owner_user_id,
                inputs=action_inputs,
                config=dict(node_data.get("config_json") or node_data.get("configJson") or {}),
                approval_mode=str(node_data.get("approval_mode") or node_data.get("approvalMode") or "never"),
                artifact_ids=self._execution_action_artifact_ids(action_inputs),
                credential_id=node_data.get("credential_id") or node_data.get("credentialId"),
                approved=approved,
                db=self._db,
            ),
        )
        if action_result.status == "pending_approval":
            run.status = "paused"
            self._add_state_snapshot(
                run_id=str(run.id),
                node_id=node_id,
                state=state,
                extra_redaction_values=extra_redaction_values,
            )
            self._add_event(
                run_id=str(run.id),
                node_id=node_id,
                event_type="execution_action_pending_approval",
                payload={
                    "type": "execution_action_pending_approval",
                    "action_key": action_key,
                    "idempotency_key": action_result.idempotency_key,
                },
                extra_redaction_values=extra_redaction_values,
            )
            return action_result

        if action_result.status != "succeeded":
            raise ValueError(action_result.error_message or f"Execution action failed: {action_key}")

        action_output = action_result.output_json if isinstance(action_result.output_json, dict) else {}
        NodeOutputStore(self._db).store_output(
            run_id=str(run.id),
            node_id=node_id,
            output=action_output,
            state=state,
        )
        self._add_state_snapshot(
            run_id=str(run.id),
            node_id=node_id,
            state=state,
            extra_redaction_values=extra_redaction_values,
        )
        self._add_event(
            run_id=str(run.id),
            node_id=node_id,
            event_type="execution_action_completed",
            payload={"type": "execution_action_completed", "action_key": action_key, "output": action_output},
            extra_redaction_values=extra_redaction_values,
        )
        return action_result

    def _google_drive_token_for_execution_action(
        self,
        *,
        node: dict[str, Any],
        owner_user_id: str,
        approved: bool,
    ):
        node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
        action_key = str(node_data.get("action_key") or node_data.get("actionKey") or "")
        if action_key != "ax.google_drive_upload":
            return None
        approval_mode = str(node_data.get("approval_mode") or node_data.get("approvalMode") or "never")
        if approval_mode == "every_run" and not approved:
            return None
        if approval_mode not in {"never", "every_run"}:
            return None
        return resolve_google_drive_runtime_token(self._db, owner_user_id=owner_user_id)

    def _execution_action_inputs(
        self,
        *,
        node_id: str,
        node_data: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        bindings = node_data.get("input_bindings") or node_data.get("inputBindings") or {}
        if not isinstance(bindings, dict):
            return {}

        resolved: dict[str, Any] = {}
        for input_name, mapping in bindings.items():
            if not isinstance(mapping, dict):
                continue
            source = mapping.get("source")
            if source == "literal":
                resolved[str(input_name)] = mapping.get("value")
            elif source == "state":
                resolved[str(input_name)] = read_path(state.get("state", {}), mapping.get("path"))
            elif source == "node":
                source_node_id = str(mapping.get("nodeId") or "")
                resolved[str(input_name)] = read_path(
                    {"output": state.get("node_outputs", {}).get(source_node_id)},
                    mapping.get("path"),
                )
            else:
                raise ValueError(f"Execution Action node {node_id} has unsupported input source: {source}")
        return resolved

    def _execution_action_artifact_ids(self, inputs: dict[str, Any]) -> list[str]:
        artifact_ids: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, str):
                if value.startswith("artifact"):
                    artifact_ids.append(value)
                return
            if isinstance(value, dict):
                artifact_id = value.get("artifact_id")
                if isinstance(artifact_id, str):
                    artifact_ids.append(artifact_id)
                for item in value.values():
                    collect(item)
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)

        collect(inputs)
        return artifact_ids

    def _pause_for_human(
        self,
        *,
        run: FlowRun,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        extra_redaction_values: set[str] | None = None,
    ) -> None:
        node_id = str(node.get("id"))
        contracts = snapshot.get("hitl_contracts") if isinstance(snapshot.get("hitl_contracts"), dict) else {}
        contract = contracts.get(node_id, {}) if isinstance(contracts, dict) else {}
        node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
        source_node_id = self._previous_crew_node_id(snapshot=snapshot, hitl_node_id=node_id)
        output_store = NodeOutputStore(self._db)
        preview_payload_ref = output_store.current_ref(run_id=str(run.id), node_id=source_node_id)
        state_output = state.get("node_outputs", {}).get(source_node_id, {})
        if preview_payload_ref is None:
            preview_payload_ref = output_store.store_output(
                run_id=str(run.id),
                node_id=source_node_id,
                output=state_output,
                state=state,
            )
        elif isinstance(state_output, dict) and output_store.resolve_output(
            run_id=str(run.id),
            ref=preview_payload_ref,
        ) != state_output:
            preview_payload_ref = output_store.store_output(
                run_id=str(run.id),
                node_id=source_node_id,
                output=state_output,
                state=state,
            )
        attempt_number = self._next_attempt_number(run_id=str(run.id), hitl_node_id=node_id)
        max_attempts = int(contract.get("maxAttempts") or node_data.get("maxAttempts") or 3)
        retry_metadata = retry_budget_metadata(
            attempt_number=attempt_number,
            max_attempts=max_attempts,
        )
        resume_path_index = self._path_index_after_node(snapshot=snapshot, node_id=node_id)
        prompt_json = redact_event_payload(
            {
                "message": HITL_MESSAGE,
                "preview_payload_ref": preview_payload_ref,
                "source_node_id": source_node_id,
                "next_node_id": self._next_node_id(snapshot=snapshot, node_id=node_id),
                "resume_path_index": resume_path_index,
                "method_name": f"hitl:{node_id}",
                **retry_metadata,
            },
            extra_values=tuple(extra_redaction_values or ()),
        )
        request = HumanFeedbackRequest(
            run_id=run.id,
            node_id=node_id,
            status="pending",
            prompt_json=prompt_json,
            response_json={},
            attempt_number=attempt_number,
        )
        run.status = "waiting_for_human"
        self._db.add(request)
        self._db.flush()
        self._add_state_snapshot(
            run_id=str(run.id),
            node_id=node_id,
            state=state,
            extra_redaction_values=extra_redaction_values,
        )
        self._add_event(
            run_id=str(run.id),
            node_id=node_id,
            event_type="hitl_requested",
            payload={
                "type": "hitl_requested",
                "run_id": str(run.id),
                "request_id": str(request.id),
                "node_id": node_id,
                "source_node_id": prompt_json["source_node_id"],
                "next_node_id": prompt_json["next_node_id"],
                "message": prompt_json["message"],
                "preview_payload_ref": prompt_json["preview_payload_ref"],
                "retry_count": prompt_json["retry_count"],
                "max_attempts": prompt_json["max_attempts"],
                "remaining_retries": prompt_json["remaining_retries"],
            },
            extra_redaction_values=extra_redaction_values,
        )

    def _hitl_contract(self, *, snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
        contracts = snapshot.get("hitl_contracts")
        if isinstance(contracts, dict):
            contract = contracts.get(node_id)
            if isinstance(contract, dict):
                return contract
        return {}

    def _previous_crew_node_id(self, *, snapshot: dict[str, Any], hitl_node_id: str) -> str:
        path = build_linear_path(snapshot)
        previous_crew_node_id = ""
        for node in path:
            if str(node.get("id")) == hitl_node_id:
                break
            if node.get("type") == "crew":
                previous_crew_node_id = str(node.get("id"))
        if not previous_crew_node_id:
            raise HumanFeedbackValidationError(f"HITL node {hitl_node_id} has no preceding crew node.")
        return previous_crew_node_id

    def _next_node_id(self, *, snapshot: dict[str, Any], node_id: str) -> str | None:
        path = build_linear_path(snapshot)
        for index, node in enumerate(path):
            if str(node.get("id")) == node_id:
                next_node = path[index + 1] if index + 1 < len(path) else None
                return str(next_node.get("id")) if next_node else None
        return None

    def _next_attempt_number(self, *, run_id: str, hitl_node_id: str) -> int:
        count = (
            self._db.query(HumanFeedbackRequest)
            .filter(HumanFeedbackRequest.run_id == run_id, HumanFeedbackRequest.node_id == hitl_node_id)
            .count()
        )
        return count + 1

    def _owned_run(self, *, run_id: str, owner_user_id: str) -> FlowRun:
        run = (
            self._db.query(FlowRun)
            .join(AssetVersion, AssetVersion.id == FlowRun.flow_version_id)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .filter(FlowRun.id == run_id, Asset.owner_user_id == owner_user_id)
            .one_or_none()
        )
        if run is None:
            raise LookupError(f"Flow run not found: {run_id}")
        return run

    def _feedback_result(
        self,
        *,
        request: HumanFeedbackRequest,
        outcome: str,
        feedback: str,
    ) -> dict[str, Any]:
        prompt = request.prompt_json or {}
        return {
            "source_hitl_node_id": request.node_id,
            "source_node_id": prompt.get("source_node_id"),
            "outcome": outcome,
            "feedback": feedback,
            "previous_output_ref": prompt.get("preview_payload_ref"),
            "retry_count": int(prompt.get("retry_count") or 0),
            "remaining_retries": int(prompt.get("remaining_retries") or 0),
            "timestamp": datetime.now(UTC).isoformat(),
            "method_name": prompt.get("method_name") or f"hitl:{request.node_id}",
        }

    def _latest_state(self, *, run_id: str) -> dict[str, Any]:
        snapshot = (
            self._db.query(FlowRunStateSnapshot)
            .filter(FlowRunStateSnapshot.run_id == run_id)
            .order_by(FlowRunStateSnapshot.created_at.desc(), FlowRunStateSnapshot.id.desc())
            .first()
        )
        return deepcopy(snapshot.state_json or {}) if snapshot is not None else {}

    def _human_feedback_context(
        self,
        *,
        request: HumanFeedbackRequest,
        feedback_result: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = request.prompt_json or {}
        return {
            "source_hitl_node_id": request.node_id,
            "source_node_id": prompt.get("source_node_id"),
            "outcome": feedback_result.get("outcome"),
            "feedback": feedback_result.get("feedback", ""),
            "previous_output_ref": prompt.get("preview_payload_ref"),
            "retry_count": int(prompt.get("retry_count") or 0),
            "remaining_retries": int(prompt.get("remaining_retries") or 0),
        }

    def _store_feedback_in_state(
        self,
        *,
        state: dict[str, Any],
        request: HumanFeedbackRequest,
        feedback_result: dict[str, Any],
    ) -> None:
        context = self._human_feedback_context(request=request, feedback_result=feedback_result)
        state.setdefault("human_feedback_history", []).append(context)
        bucket = state.setdefault("human_feedback", {}).setdefault(request.node_id, {"history": []})
        bucket["latest"] = context
        bucket.setdefault("history", []).append(context)

    def _path_index_after_node(self, *, snapshot: dict[str, Any], node_id: str) -> int:
        path = build_linear_path(snapshot)
        for index, node in enumerate(path):
            if str(node.get("id")) == node_id:
                return index + 1
        raise HumanFeedbackValidationError("Human feedback request references nodes outside the flow path.")

    def _path_index_for_node(self, *, snapshot: dict[str, Any], node_id: str) -> int:
        path = build_linear_path(snapshot)
        for index, node in enumerate(path):
            if str(node.get("id")) == node_id:
                return index
        raise HumanFeedbackValidationError("Human feedback request references nodes outside the flow path.")

    def _is_execution_action_approval(self, request: HumanFeedbackRequest) -> bool:
        return (request.prompt_json or {}).get("approval_type") == "execution_action"

    def _runtime_context_for_downstream(
        self,
        *,
        snapshot: dict[str, Any],
        start_index: int,
        request: HumanFeedbackRequest,
        feedback_result: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        outcome = str(feedback_result.get("outcome") or "")
        feedback = str(feedback_result.get("feedback") or "").strip()
        if outcome != "approved" or not feedback:
            return {}

        for node in build_linear_path(snapshot)[start_index:]:
            if node.get("type") == "crew":
                return {
                    str(node.get("id")): {
                        "human_feedback": self._human_feedback_context(
                            request=request,
                            feedback_result=feedback_result,
                        )
                    }
                }
            if node.get("type") in {"hitl", "output"}:
                return {}
        return {}

    def _execute_from_path_index(
        self,
        *,
        run: FlowRun,
        snapshot: dict[str, Any],
        path_index: int,
        owner_user_id: str,
        state: dict[str, Any],
        runtime_context_by_node: dict[str, dict[str, Any]] | None = None,
        llm_catalog: dict[str, Any] | None = None,
        approved_execution_action_node_ids: set[str] | None = None,
    ) -> None:
        state.setdefault("state", {})
        state.setdefault("node_outputs", {})
        state.setdefault("node_output_refs", {})
        state.setdefault("node_output_versions", {})
        state.setdefault("transfer_values", {})
        state.setdefault("human_feedback", {})
        state.setdefault("human_feedback_history", [])
        run_options = state.get("run_options") if isinstance(state.get("run_options"), dict) else {}
        capture_agent_execution_logs = run_options.get("capture_agent_execution_logs", True) is not False
        redaction_values: set[str] = set()
        failure_redaction_values: set[str] = set()
        runtime_context_by_node = runtime_context_by_node or {}
        approved_execution_action_node_ids = approved_execution_action_node_ids or set()
        active_node_id: str | None = None
        active_node_type: str | None = None

        try:
            for node in build_linear_path(snapshot)[path_index:]:
                node_type = node.get("type")
                node_id = str(node.get("id"))
                active_node_id = node_id
                active_node_type = str(node_type) if node_type is not None else None
                if node_type == "output":
                    output = build_output_payload(
                        snapshot=snapshot,
                        state=state["state"],
                        node_outputs=state["node_outputs"],
                    )
                    output = self._redact_runtime_value(output, extra_redaction_values=redaction_values)
                    state["output"] = output
                    run.output_json = output
                    run.status = "completed"
                    run.finished_at = datetime.now(UTC)
                    self._add_state_snapshot(
                        run_id=str(run.id),
                        node_id=node_id,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="run_completed",
                        payload={"output": output},
                        extra_redaction_values=redaction_values,
                    )
                    return
                if node_type == "hitl":
                    self._pause_for_human(
                        run=run,
                        snapshot=snapshot,
                        node=node,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    return
                if node_type == "execution_action":
                    action_approved = node_id in approved_execution_action_node_ids
                    drive_token = self._google_drive_token_for_execution_action(
                        node=node,
                        owner_user_id=owner_user_id,
                        approved=action_approved,
                    )
                    oauth_redaction_values = runtime_oauth_redaction_values(drive_token)
                    redaction_values.update(oauth_redaction_values)
                    failure_redaction_values.update(oauth_redaction_values)
                    action_context = (
                        google_workspace_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            drive_token=drive_token,
                        )
                        if drive_token is not None
                        else nullcontext()
                    )
                    with action_context:
                        action_result = self._execute_execution_action_node(
                            run=run,
                            node=node,
                            state=state,
                            owner_user_id=owner_user_id,
                            extra_redaction_values=redaction_values,
                            approved=action_approved,
                        )
                    if action_result.status == "pending_approval":
                        return
                    continue
                if node_type == "crew":
                    crew_snapshot = self._crew_runtime_snapshot_for_node(
                        snapshot=snapshot,
                        crew_node=node,
                        owner_user_id=owner_user_id,
                    )
                    crew_inputs = build_crew_inputs(
                        snapshot=snapshot,
                        crew_node_id=node_id,
                        state=state["state"],
                        node_outputs=state["node_outputs"],
                        runtime_context=runtime_context_by_node.get(node_id),
                    )
                    callback_redaction_values = set(redaction_values)
                    callback_redaction_values.update(self._crew_input_redaction_values(crew_inputs))
                    failure_redaction_values.update(callback_redaction_values)
                    for input_name, input_value in crew_inputs.items():
                        if isinstance(input_value, str):
                            state["transfer_values"][f"{node_id}.{input_name}"] = {
                                "type": "text",
                                "length": len(input_value),
                            }
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="crew_started",
                        payload={"inputs": self._redact_crew_inputs_for_event(crew_inputs)},
                    )
                    instrumentation_callbacks = self._instrumentation_callbacks_for_node(
                        run_id=str(run.id),
                        node_id=node_id,
                        capture_agent_execution_logs=capture_agent_execution_logs,
                        extra_redaction_values=callback_redaction_values,
                    )
                    required_providers = collect_required_credential_providers(
                        crew_snapshot=crew_snapshot,
                        llm_catalog=llm_catalog,
                    )
                    credential_env = resolve_credential_env(
                        self._db,
                        owner_user_id=owner_user_id,
                        providers=required_providers,
                    )
                    redaction_values.update(value for value in credential_env.values() if value)
                    callback_redaction_values.update(value for value in credential_env.values() if value)
                    failure_redaction_values.update(value for value in credential_env.values() if value)
                    sheets_token = resolve_google_sheets_runtime_token_for_crew(
                        self._db,
                        owner_user_id=owner_user_id,
                        crew_snapshot=crew_snapshot,
                    )
                    instagram_token = resolve_meta_instagram_runtime_token_for_crew(
                        self._db,
                        owner_user_id=owner_user_id,
                        crew_snapshot=crew_snapshot,
                    )
                    oauth_redaction_values = runtime_oauth_redaction_values(sheets_token, instagram_token)
                    redaction_values.update(oauth_redaction_values)
                    callback_redaction_values.update(oauth_redaction_values)
                    failure_redaction_values.update(oauth_redaction_values)
                    event_writer = self._event_writer(
                        extra_redaction_values=tuple(callback_redaction_values)
                    )
                    with (
                        runtime_env_overlay(credential_env),
                        google_workspace_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            sheets_token=sheets_token,
                        ),
                        meta_instagram_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            run_id=str(run.id),
                            token=instagram_token,
                        ),
                        nano_banana_artifact_runtime_context(
                            db=self._db,
                            owner_user_id=owner_user_id,
                            run_id=str(run.id),
                            node_id=node_id,
                        ),
                    ):
                        crew = CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog, db=self._db).build_crew(
                            runtime_crew=crew_snapshot.get("runtime_crew", {}),
                            runtime_agents=crew_snapshot.get("runtime_agents", {}),
                            runtime_tasks=crew_snapshot.get("runtime_tasks", {}),
                            task_agent_links=crew_snapshot.get("task_agent_links", {}),
                            agent_tool_links=self._agent_tool_links_for_crew_snapshot(crew_snapshot),
                            task_tool_links=crew_snapshot.get("task_tool_links", {}),
                            runtime_tools=crew_snapshot.get("runtime_tools", {}),
                            agent_knowledge_links=crew_snapshot.get("agent_knowledge_links", {}),
                            runtime_knowledge=crew_snapshot.get("runtime_knowledge", {}),
                            instrumentation_callbacks=instrumentation_callbacks,
                        )
                        with crewai_event_bridge(
                            writer=event_writer,
                            run_id=str(run.id),
                            node_id=node_id,
                        ):
                            crew_output = self._redact_runtime_value(
                                normalize_crew_output(crew.kickoff(inputs=crew_inputs)),
                                extra_redaction_values=redaction_values,
                            )
                    NodeOutputStore(self._db).store_output(
                        run_id=str(run.id),
                        node_id=node_id,
                        output=crew_output,
                        state=state,
                    )
                    self._add_state_snapshot(
                        run_id=str(run.id),
                        node_id=node_id,
                        state=state,
                        extra_redaction_values=redaction_values,
                    )
                    self._add_event(
                        run_id=str(run.id),
                        node_id=node_id,
                        event_type="crew_completed",
                        payload={"output": crew_output},
                        extra_redaction_values=redaction_values,
                    )
                    continue
                raise UnsupportedGraphError(f"Unsupported flow runtime node type: {node_type}")
        except (UnsupportedGraphError, HumanFeedbackValidationError, CredentialResolutionError):
            raise
        except Exception as exc:
            redacted_error = redact_secret_text(str(exc), extra_values=tuple(failure_redaction_values))
            run.status = "failed"
            run.error_message = redacted_error
            run.finished_at = datetime.now(UTC)
            if active_node_type == "crew" and active_node_id is not None:
                self._add_event(
                    run_id=str(run.id),
                    node_id=active_node_id,
                    event_type="crew_failed",
                    payload={
                        "type": "crew_failed",
                        "run_id": str(run.id),
                        "node_id": active_node_id,
                        "error_message": redacted_error,
                        "fatal": True,
                    },
                    extra_redaction_values=failure_redaction_values,
                )
            self._add_event(
                run_id=str(run.id),
                node_id=active_node_id,
                event_type="run_failed",
                payload={
                    "type": "run_failed",
                    "run_id": str(run.id),
                    "node_id": active_node_id,
                    "error_message": redacted_error,
                    "error": redacted_error,
                },
                extra_redaction_values=failure_redaction_values,
            )
            return

    def _latest_output_for_request(self, *, run_id: str, request: HumanFeedbackRequest) -> dict[str, Any]:
        state = self._latest_state(run_id=run_id)
        source_node_id = (request.prompt_json or {}).get("source_node_id")
        if isinstance(source_node_id, str):
            output = (state.get("node_outputs") or {}).get(source_node_id)
            if isinstance(output, dict):
                return output
        return {}

    def _complete_approved_run(self, *, run: FlowRun, owner_user_id: str) -> None:
        snapshot = self.load_published_snapshot(
            flow_version_id=str(run.flow_version_id),
            owner_user_id=owner_user_id,
        )
        state = self._latest_state(run_id=str(run.id))
        state.setdefault("state", {})
        state.setdefault("node_outputs", {})
        output = build_output_payload(
            snapshot=snapshot,
            state=state["state"],
            node_outputs=state["node_outputs"],
        )
        state["output"] = output
        output_node_id = self._output_node_id(snapshot=snapshot)
        run.status = "completed"
        run.output_json = output
        run.finished_at = datetime.now(UTC)
        self._add_state_snapshot(run_id=str(run.id), node_id=output_node_id, state=state)
        self._add_event(
            run_id=str(run.id),
            node_id=output_node_id,
            event_type="run_completed",
            payload={"output": output},
        )

    def _output_node_id(self, *, snapshot: dict[str, Any]) -> str:
        for node in build_linear_path(snapshot):
            if node.get("type") == "output":
                return str(node.get("id"))
        raise UnsupportedGraphError("Flow runtime graph must contain exactly one output node on the linear path.")

    def _retry_previous_crew(
        self,
        *,
        run: FlowRun,
        request: HumanFeedbackRequest,
        feedback_result: dict[str, Any],
        llm_catalog: dict[str, Any] | None,
    ) -> None:
        prompt = request.prompt_json or {}
        owner_user_id = self._owner_user_id_for_run(run)
        snapshot = self.load_published_snapshot(
            flow_version_id=str(run.flow_version_id),
            owner_user_id=owner_user_id,
        )
        source_node_id = str(prompt.get("source_node_id") or "")
        path_nodes = {str(node.get("id")): node for node in build_linear_path(snapshot)}
        crew_node = path_nodes.get(source_node_id)
        hitl_node = path_nodes.get(request.node_id)
        if crew_node is None or hitl_node is None:
            raise HumanFeedbackValidationError("Human feedback request references nodes outside the flow path.")

        state = self._latest_state(run_id=str(run.id))
        state.setdefault("state", {})
        state.setdefault("node_outputs", {})
        self._store_feedback_in_state(state=state, request=request, feedback_result=feedback_result)
        run_options = state.get("run_options") if isinstance(state.get("run_options"), dict) else {}
        capture_agent_execution_logs = run_options.get("capture_agent_execution_logs", True) is not False
        crew_inputs = build_crew_inputs(
            snapshot=snapshot,
            crew_node_id=source_node_id,
            state=state["state"],
            node_outputs=state["node_outputs"],
        )
        human_feedback = self._human_feedback_context(
            request=request,
            feedback_result=feedback_result,
        )
        if str(human_feedback.get("feedback") or "").strip():
            crew_inputs["human_feedback"] = human_feedback
        redaction_values: set[str] = set()
        callback_redaction_values = self._crew_input_redaction_values(crew_inputs)
        failure_redaction_values = set(callback_redaction_values)
        crew_snapshot = self._crew_runtime_snapshot_for_node(
            snapshot=snapshot,
            crew_node=crew_node,
            owner_user_id=owner_user_id,
        )
        self._add_event(
            run_id=str(run.id),
            node_id=source_node_id,
            event_type="crew_retry_started",
            payload={"inputs": self._redact_crew_inputs_for_event(crew_inputs)},
        )
        instrumentation_callbacks = self._instrumentation_callbacks_for_node(
            run_id=str(run.id),
            node_id=source_node_id,
            capture_agent_execution_logs=capture_agent_execution_logs,
            extra_redaction_values=callback_redaction_values,
        )
        required_providers = collect_required_credential_providers(
            crew_snapshot=crew_snapshot,
            llm_catalog=llm_catalog,
        )
        credential_env = resolve_credential_env(
            self._db,
            owner_user_id=owner_user_id,
            providers=required_providers,
        )
        redaction_values.update(value for value in credential_env.values() if value)
        callback_redaction_values.update(value for value in credential_env.values() if value)
        failure_redaction_values.update(value for value in credential_env.values() if value)
        sheets_token = resolve_google_sheets_runtime_token_for_crew(
            self._db,
            owner_user_id=owner_user_id,
            crew_snapshot=crew_snapshot,
        )
        instagram_token = resolve_meta_instagram_runtime_token_for_crew(
            self._db,
            owner_user_id=owner_user_id,
            crew_snapshot=crew_snapshot,
        )
        oauth_redaction_values = runtime_oauth_redaction_values(sheets_token, instagram_token)
        redaction_values.update(oauth_redaction_values)
        callback_redaction_values.update(oauth_redaction_values)
        failure_redaction_values.update(oauth_redaction_values)
        event_writer = self._event_writer(extra_redaction_values=tuple(callback_redaction_values))
        try:
            with (
                runtime_env_overlay(credential_env),
                google_workspace_runtime_context(
                    db=self._db,
                    owner_user_id=owner_user_id,
                    sheets_token=sheets_token,
                ),
                meta_instagram_runtime_context(
                    db=self._db,
                    owner_user_id=owner_user_id,
                    run_id=str(run.id),
                    token=instagram_token,
                ),
                nano_banana_artifact_runtime_context(
                    db=self._db,
                    owner_user_id=owner_user_id,
                    run_id=str(run.id),
                    node_id=source_node_id,
                ),
            ):
                crew = CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog, db=self._db).build_crew(
                    runtime_crew=crew_snapshot.get("runtime_crew", {}),
                    runtime_agents=crew_snapshot.get("runtime_agents", {}),
                    runtime_tasks=crew_snapshot.get("runtime_tasks", {}),
                    task_agent_links=crew_snapshot.get("task_agent_links", {}),
                    agent_tool_links=self._agent_tool_links_for_crew_snapshot(crew_snapshot),
                    task_tool_links=crew_snapshot.get("task_tool_links", {}),
                    runtime_tools=crew_snapshot.get("runtime_tools", {}),
                    agent_knowledge_links=crew_snapshot.get("agent_knowledge_links", {}),
                    runtime_knowledge=crew_snapshot.get("runtime_knowledge", {}),
                    instrumentation_callbacks=instrumentation_callbacks,
                )
                with crewai_event_bridge(
                    writer=event_writer,
                    run_id=str(run.id),
                    node_id=source_node_id,
                ):
                    crew_output = self._redact_runtime_value(
                        normalize_crew_output(crew.kickoff(inputs=crew_inputs)),
                        extra_redaction_values=redaction_values,
                    )
        except Exception as exc:
            redacted_error = redact_secret_text(str(exc), extra_values=tuple(failure_redaction_values))
            run.status = "failed"
            run.error_message = redacted_error
            run.finished_at = datetime.now(UTC)
            self._add_state_snapshot(
                run_id=str(run.id),
                node_id=source_node_id,
                state=state,
                extra_redaction_values=failure_redaction_values,
            )
            self._add_event(
                run_id=str(run.id),
                node_id=source_node_id,
                event_type="crew_failed",
                payload={
                    "type": "crew_failed",
                    "run_id": str(run.id),
                    "node_id": source_node_id,
                    "error_message": redacted_error,
                    "fatal": True,
                },
                extra_redaction_values=failure_redaction_values,
            )
            self._add_event(
                run_id=str(run.id),
                node_id=source_node_id,
                event_type="run_failed",
                payload={
                    "type": "run_failed",
                    "run_id": str(run.id),
                    "node_id": source_node_id,
                    "error_message": redacted_error,
                    "error": redacted_error,
                },
                extra_redaction_values=failure_redaction_values,
            )
            return
        NodeOutputStore(self._db).store_output(
            run_id=str(run.id),
            node_id=source_node_id,
            output=crew_output,
            state=state,
        )
        self._add_state_snapshot(
            run_id=str(run.id),
            node_id=source_node_id,
            state=state,
            extra_redaction_values=redaction_values,
        )
        self._add_event(
            run_id=str(run.id),
            node_id=source_node_id,
            event_type="crew_completed",
            payload={"output": crew_output},
            extra_redaction_values=redaction_values,
        )
        self._pause_for_human(
            run=run,
            snapshot=snapshot,
            node=hitl_node,
            state=state,
            extra_redaction_values=redaction_values,
        )

    def _redact_runtime_value(self, value: Any, *, extra_redaction_values: set[str] | None = None) -> Any:
        return redact_event_payload(
            {"value": value},
            extra_values=tuple(extra_redaction_values or ()),
        )["value"]

    def _owner_user_id_for_run(self, run: FlowRun) -> str:
        row = (
            self._db.query(Asset.owner_user_id)
            .select_from(Asset)
            .join(AssetVersion, AssetVersion.asset_id == Asset.id)
            .filter(AssetVersion.id == run.flow_version_id)
            .one()
        )
        return str(row.owner_user_id)

    def _agent_tool_links_for_crew_snapshot(self, crew_snapshot: dict[str, Any]) -> Any:
        agent_tool_links = crew_snapshot.get("agent_tool_links")
        if agent_tool_links:
            return agent_tool_links
        return crew_snapshot.get("tool_links", {})
