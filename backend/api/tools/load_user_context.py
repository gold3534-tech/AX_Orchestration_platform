from crewai.tools import BaseTool
from pydantic import BaseModel


class LoadUserContextInput(BaseModel):
    user_id: str


class LoadUserContextTool(BaseTool):
    name: str = "load_user_context"
    description: str = "사용자 컨텍스트 정보를 로드합니다"
    args_schema: type[BaseModel] = LoadUserContextInput

    def _run(self, user_id: str) -> str:
        return f"[load_user_context stub] user_id='{user_id}' — no context loaded yet"
