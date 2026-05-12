from __future__ import annotations

import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BACKEND_FILES = [
    BACKEND_ROOT / "api/routes/assets.py",
    BACKEND_ROOT / "api/routes/runtime.py",
    BACKEND_ROOT / "api/routes/runs.py",
    BACKEND_ROOT / "api/routes/tooling.py",
    BACKEND_ROOT / "api/routes/crew_graphs.py",
    BACKEND_ROOT / "api/routes/flow_graphs.py",
    BACKEND_ROOT / "api/services/assets.py",
    BACKEND_ROOT / "api/services/runs.py",
    BACKEND_ROOT / "api/services/tooling.py",
    BACKEND_ROOT / "api/services/crew_graphs.py",
    BACKEND_ROOT / "api/services/flow_graphs.py",
    BACKEND_ROOT / "api/runtime/crewai_factory.py",
    BACKEND_ROOT / "api/runtime/loaders/crew_graph_loader.py",
    BACKEND_ROOT / "api/runtime/loaders/flow_graph_loader.py",
]
LEGACY_REPOSITORY_FILES = [
    BACKEND_ROOT / "api/repositories/agents.py",
    BACKEND_ROOT / "api/repositories/tasks.py",
    BACKEND_ROOT / "api/repositories/crews.py",
    BACKEND_ROOT / "api/repositories/flows.py",
    BACKEND_ROOT / "api/repositories/task_agents.py",
    BACKEND_ROOT / "api/repositories/flow_crews.py",
    BACKEND_ROOT / "api/repositories/skills.py",
    BACKEND_ROOT / "api/repositories/tools.py",
    BACKEND_ROOT / "api/repositories/input_presets.py",
    BACKEND_ROOT / "api/repositories/runs.py",
]
REPOSITORY_IMPORT_MARKERS = (
    "api.repositories",
    "from .repositories",
    "from ..repositories",
    "from api.repositories",
)


def test_legacy_repository_modules_are_deleted() -> None:
    missing = [path for path in LEGACY_REPOSITORY_FILES if not path.exists()]
    assert missing == LEGACY_REPOSITORY_FILES


def test_canonical_backend_paths_do_not_import_repository_layer() -> None:
    for path in CANONICAL_BACKEND_FILES:
        source = path.read_text()
        assert not any(marker in source for marker in REPOSITORY_IMPORT_MARKERS), (
            f"{path} should not import the legacy repository layer"
        )


def test_runtime_graph_loader_is_deleted_and_not_imported() -> None:
    graph_loader_path = BACKEND_ROOT / "api/runtime/graph_loader.py"
    assert not graph_loader_path.exists()

    standalone_graph_loader_constructor = re.compile(r"(?<![A-Za-z0-9_])GraphLoader\s*\(")
    forbidden_markers = (
        "api.runtime.graph_loader",
        "from api.runtime.graph_loader",
        "import GraphLoader",
        "load_flow_graph(",
    )
    for path in CANONICAL_BACKEND_FILES:
        source = path.read_text()
        assert not any(marker in source for marker in forbidden_markers), (
            f"{path} should not depend on the legacy graph loader"
        )
        assert standalone_graph_loader_constructor.search(source) is None, (
            f"{path} should not depend on the legacy graph loader"
        )
