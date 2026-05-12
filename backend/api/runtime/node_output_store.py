from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.db.models import FlowRunNodeOutput


class NodeOutputStore:
    def __init__(self, db: Session):
        self._db = db

    def store_output(
        self,
        *,
        run_id: str,
        node_id: str,
        output: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        next_version = self._next_version(run_id=run_id, node_id=node_id)
        self._db.query(FlowRunNodeOutput).filter(
            FlowRunNodeOutput.run_id == run_id,
            FlowRunNodeOutput.node_id == node_id,
            FlowRunNodeOutput.status == "current",
        ).update({FlowRunNodeOutput.status: "superseded"}, synchronize_session=False)
        row = FlowRunNodeOutput(
            run_id=run_id,
            node_id=node_id,
            version=next_version,
            output_json=output,
            status="current",
        )
        self._db.add(row)
        self._db.flush()
        ref = {"node_id": node_id, "version": next_version}
        if state is not None:
            self.update_state_with_ref(state=state, node_id=node_id, output=output, ref=ref)
        return ref

    def resolve_output(self, *, run_id: str, ref: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(ref, dict):
            return {}
        node_id = str(ref.get("node_id") or "")
        version = ref.get("version")
        if not node_id or version is None:
            return {}
        try:
            version_number = int(version)
        except (TypeError, ValueError):
            return {}
        row = (
            self._db.query(FlowRunNodeOutput)
            .filter(
                FlowRunNodeOutput.run_id == run_id,
                FlowRunNodeOutput.node_id == node_id,
                FlowRunNodeOutput.version == version_number,
            )
            .one_or_none()
        )
        return row.output_json if row is not None and isinstance(row.output_json, dict) else {}

    def current_ref(self, *, run_id: str, node_id: str) -> dict[str, Any] | None:
        row = (
            self._db.query(FlowRunNodeOutput)
            .filter(
                FlowRunNodeOutput.run_id == run_id,
                FlowRunNodeOutput.node_id == node_id,
                FlowRunNodeOutput.status == "current",
            )
            .order_by(FlowRunNodeOutput.version.desc())
            .first()
        )
        if row is None:
            return None
        return {"node_id": row.node_id, "version": row.version}

    def update_state_with_ref(
        self,
        *,
        state: dict[str, Any],
        node_id: str,
        output: dict[str, Any],
        ref: dict[str, Any],
    ) -> None:
        state.setdefault("node_outputs", {})[node_id] = output
        state.setdefault("node_output_refs", {})[node_id] = {
            "current_version": ref["version"],
            "output_ref": ref,
        }
        versions = state.setdefault("node_output_versions", {}).setdefault(node_id, [])
        for version_entry in versions:
            version_entry["status"] = "superseded"
        versions.append({"version": ref["version"], "status": "current"})

    def _next_version(self, *, run_id: str, node_id: str) -> int:
        row = (
            self._db.query(FlowRunNodeOutput)
            .filter(FlowRunNodeOutput.run_id == run_id, FlowRunNodeOutput.node_id == node_id)
            .order_by(FlowRunNodeOutput.version.desc())
            .first()
        )
        return 1 if row is None else int(row.version) + 1
