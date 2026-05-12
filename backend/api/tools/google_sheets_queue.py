from __future__ import annotations

import re
from typing import Any

_SAFE_SHEET_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def pending_status_updates(
    rows: list[list[Any]],
    *,
    sheet_name: str,
    link_column: str,
    status_column: str,
    pending_value: str = "pending",
    done_value: str = "done",
) -> list[dict[str, Any]]:
    sheet_name = _required_sheet_name(sheet_name)
    if not rows:
        return []
    header = [str(value).strip() for value in rows[0]]
    link_index = _required_header_index(header, link_column)
    status_index = _required_header_index(header, status_column)

    updates: list[dict[str, Any]] = []
    for offset, row in enumerate(rows[1:], start=2):
        status = _cell_value(row, status_index).strip()
        partner_link = _cell_value(row, link_index).strip()
        if status != pending_value or not partner_link:
            continue
        updates.append(
            {
                "row_number": offset,
                "partner_link": partner_link,
                "range_name": (
                    f"{_format_sheet_name_for_a1(sheet_name)}!"
                    f"{_column_letter(status_index)}{offset}"
                ),
                "values": [[done_value]],
            }
        )
    return updates


def _required_header_index(header: list[str], column_name: str) -> int:
    normalized = column_name.strip()
    try:
        return header.index(normalized)
    except ValueError as exc:
        raise ValueError(f"Missing required Google Sheets header: {normalized}") from exc


def _required_sheet_name(sheet_name: str) -> str:
    if not isinstance(sheet_name, str) or not sheet_name.strip():
        raise ValueError("sheet_name must not be empty")
    return sheet_name.strip()


def _format_sheet_name_for_a1(sheet_name: str) -> str:
    if _SAFE_SHEET_NAME_PATTERN.fullmatch(sheet_name):
        return sheet_name
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


def _cell_value(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    value = row[index]
    return value if isinstance(value, str) else str(value)


def _column_letter(index: int) -> str:
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
