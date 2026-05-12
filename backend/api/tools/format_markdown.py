from crewai.tools import BaseTool
from pydantic import BaseModel


class FormatMarkdownInput(BaseModel):
    text: str


class FormatMarkdownTool(BaseTool):
    name: str = "format_markdown"
    description: str = "텍스트를 마크다운 형식으로 변환합니다"
    args_schema: type[BaseModel] = FormatMarkdownInput

    def _run(self, text: str) -> str:
        return f"[format_markdown stub] text='{text[:50]}' — passthrough"
