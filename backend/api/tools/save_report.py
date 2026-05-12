from crewai.tools import BaseTool
from pydantic import BaseModel


class SaveReportInput(BaseModel):
    content: str
    filename: str


class SaveReportTool(BaseTool):
    name: str = "save_report"
    description: str = "결과 보고서를 저장합니다"
    args_schema: type[BaseModel] = SaveReportInput

    def _run(self, content: str, filename: str) -> str:
        return f"[save_report stub] filename='{filename}' — not persisted yet"
