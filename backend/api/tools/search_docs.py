from crewai.tools import BaseTool
from pydantic import BaseModel


class SearchDocsInput(BaseModel):
    query: str


class SearchDocsTool(BaseTool):
    name: str = "search_docs"
    description: str = "등록된 문서에서 관련 내용을 검색합니다"
    args_schema: type[BaseModel] = SearchDocsInput

    def _run(self, query: str) -> str:
        return f"[search_docs stub] query='{query}' — no documents indexed yet"
