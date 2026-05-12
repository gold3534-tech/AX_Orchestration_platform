import pytest

from api.tools.google_sheets_queue import pending_status_updates


def test_pending_status_updates_builds_single_cell_done_updates():
    rows = [
        ["product_name", "partner_link", "post_status"],
        ["Lamp", "https://example.com/lamp", "pending"],
        ["Chair", "https://example.com/chair", "done"],
        ["Desk", "https://example.com/desk", "pending"],
    ]

    updates = pending_status_updates(
        rows,
        sheet_name="Sheet1",
        link_column="partner_link",
        status_column="post_status",
        pending_value="pending",
        done_value="done",
    )

    assert updates == [
        {
            "row_number": 2,
            "partner_link": "https://example.com/lamp",
            "range_name": "Sheet1!C2",
            "values": [["done"]],
        },
        {
            "row_number": 4,
            "partner_link": "https://example.com/desk",
            "range_name": "Sheet1!C4",
            "values": [["done"]],
        },
    ]


def test_pending_status_updates_skips_blank_links_and_done_rows():
    rows = [
        ["partner_link", "post_status"],
        ["", "pending"],
        ["https://example.com/done", "done"],
        ["https://example.com/pending", "pending"],
    ]

    updates = pending_status_updates(
        rows,
        sheet_name="Queue",
        link_column="partner_link",
        status_column="post_status",
    )

    assert updates == [
        {
            "row_number": 4,
            "partner_link": "https://example.com/pending",
            "range_name": "Queue!B4",
            "values": [["done"]],
        }
    ]


def test_pending_status_updates_requires_expected_headers():
    rows = [["url", "status"], ["https://example.com", "pending"]]

    with pytest.raises(
        ValueError,
        match="^Missing required Google Sheets header: partner_link$",
    ):
        pending_status_updates(
            rows,
            sheet_name="Sheet1",
            link_column="partner_link",
            status_column="post_status",
        )


def test_pending_status_updates_requires_sheet_name_even_with_empty_rows():
    with pytest.raises(ValueError, match="^sheet_name must not be empty$"):
        pending_status_updates(
            [],
            sheet_name="",
            link_column="partner_link",
            status_column="post_status",
        )


def test_pending_status_updates_quotes_sheet_names_with_spaces():
    updates = pending_status_updates(
        [
            ["partner_link", "post_status"],
            ["https://example.com/pending", "pending"],
        ],
        sheet_name="Content Queue",
        link_column="partner_link",
        status_column="post_status",
    )

    assert updates[0]["range_name"] == "'Content Queue'!B2"


def test_pending_status_updates_escapes_single_quotes_in_sheet_names():
    updates = pending_status_updates(
        [
            ["partner_link", "post_status"],
            ["https://example.com/pending", "pending"],
        ],
        sheet_name="Partner's Queue",
        link_column="partner_link",
        status_column="post_status",
    )

    assert updates[0]["range_name"] == "'Partner''s Queue'!B2"
