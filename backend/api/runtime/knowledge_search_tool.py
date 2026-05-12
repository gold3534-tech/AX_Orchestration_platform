from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crewai.tools import BaseTool
from pydantic import PrivateAttr


class AXKnowledgeSearchTool(BaseTool):
    name: str = "AX Knowledge Search"
    description: str = (
        "Search and read only the uploaded Knowledge Sources attached to this Agent. "
        "Use this before answering questions about attached PDFs, RFPs, internal documents, "
        "policies, requirements, or private knowledge. Returns matching passages with source metadata."
    )

    _knowledge_item_ids: list[str] = PrivateAttr(default_factory=list)
    _search_fn: Callable[[str, list[str], int], list[dict[str, Any]]] = PrivateAttr()
    _top_k: int = PrivateAttr(default=5)

    def __init__(
        self,
        *,
        knowledge_item_ids: list[str],
        search_fn: Callable[[str, list[str], int], list[dict[str, Any]]],
        top_k: int = 5,
    ):
        super().__init__()
        self._knowledge_item_ids = list(dict.fromkeys(knowledge_item_ids))
        self._search_fn = search_fn
        self._top_k = top_k

    def _run(self, query: str) -> dict[str, Any]:
        if not query or not query.strip():
            return {"matches": []}
        try:
            matches = self._search_fn(query.strip(), self._knowledge_item_ids, self._top_k)
        except Exception:
            return {"matches": [], "error": "Knowledge search is unavailable."}
        return {"matches": matches}
