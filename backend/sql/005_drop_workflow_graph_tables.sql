-- Remove legacy workflow graph persistence.
-- Draft builder state is stored in crew_version_drafts.graph_json and flow_version_drafts.graph_json.
-- Published runtime execution state is stored in asset_runtime_snapshots.runtime_snapshot_json.

DROP TABLE IF EXISTS workflow_edges CASCADE;
DROP TABLE IF EXISTS workflow_nodes CASCADE;
