from __future__ import annotations

from typing import Any, Literal, TypeAlias

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from api.integrations.google_workspace import build_sheets_client_from_runtime

GoogleSheetsCellValue: TypeAlias = str | int | float | bool | None


class GoogleSheetsInput(BaseModel):
    operation: Literal["read_range", "append_rows", "update_values"] = Field(
        description="Operation to perform. Use read_range before updating rows you need to inspect."
    )
    spreadsheet_id: str = Field(
        description="Google spreadsheet ID from the URL. Do not include the full spreadsheet URL."
    )
    range_name: str = Field(
        description=(
            "A1 notation range only, such as products!A20:C22 or products!C20. "
            "Use the exact sheet tab name. Do not include braces, markdown, quotes, "
            "trailing punctuation, or explanatory text."
        )
    )
    values: list[list[GoogleSheetsCellValue]] | None = Field(
        default=None,
        description=(
            "Required for append_rows and update_values. Must be a list of rows, "
            'for example [["done"]], not ["done"]. Omit or null for read_range.'
        ),
    )


class AXGoogleSheetsTool(BaseTool):
    name: str = "ax_google_sheets"
    description: str = (
        "Read, append rows to, or update values in Google Sheets through the connected "
        "user's Google Workspace account. Use exact A1 notation for range_name, for "
        "example products!A20:C22 or products!C20. Do not include braces, markdown, "
        "quotes, or trailing punctuation in range_name. For updates, values must be "
        'a list of rows such as [["done"]].'
    )
    args_schema: type[BaseModel] = GoogleSheetsInput
    read_range_enabled: bool = True
    append_rows_enabled: bool = True
    update_values_enabled: bool = True

    def _run(
        self,
        operation: str,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]] | None = None,
    ) -> list[list[Any]] | dict[str, Any]:
        spreadsheet_id = self._required_string(spreadsheet_id, "spreadsheet_id")
        range_name = self._required_string(range_name, "range_name")
        self._validate_operation_enabled(operation)
        if operation in {"append_rows", "update_values"}:
            values = self._required_values(values)
        client = build_sheets_client_from_runtime()
        if operation == "read_range":
            return client.read_range(spreadsheet_id, range_name)
        if operation == "append_rows":
            return client.append_rows(spreadsheet_id, range_name, values)
        if operation == "update_values":
            return client.update_values(spreadsheet_id, range_name, values)
        raise ValueError(f"Unsupported Google Sheets operation: {operation}")

    def _validate_operation_enabled(self, operation: str) -> None:
        if operation == "read_range" and not self.read_range_enabled:
            raise ValueError("read_range is disabled")
        if operation == "append_rows" and not self.append_rows_enabled:
            raise ValueError("append_rows is disabled")
        if operation == "update_values" and not self.update_values_enabled:
            raise ValueError("update_values is disabled")

    def _required_string(self, value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty")
        return value.strip()

    def _required_values(self, values: list[list[Any]] | None) -> list[list[Any]]:
        if not isinstance(values, list) or not all(isinstance(row, list) for row in values):
            raise ValueError("values must be a list of rows for write operations")
        return values
