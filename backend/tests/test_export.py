"""Tests for FinSight CSV export endpoint (FR-IO-01).

Covers /export/csv: streaming CSV download with optional filters and RFC 4180
escaping, scoped to the authenticated caller.
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from .helpers import auth_headers

EXPECTED_HEADER = (
    "id,occurred_at,description,category,amount,currency,amount_base,is_business,source"
)


VALID_BODY = {
    "amount": "12.50",
    "currency": "PEN",
    "description": "Lunch at corner cafe",
}


async def _create(
    client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload = {**VALID_BODY, **overrides}
    response = await client.post("/expenses", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _parse_csv(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))


# --- Auth & response shape ---------------------------------------------------


async def test_export_requires_auth_returns_401(client: AsyncClient) -> None:
    response = await client.get("/export/csv")
    assert response.status_code == 401


async def test_export_returns_text_csv_content_type(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].lower() == "text/csv; charset=utf-8"


async def test_export_returns_attachment_disposition(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    # Use UTC date to match the service's `datetime.now(tz=UTC).date()` —
    # avoids a flaky failure when CI crosses midnight UTC.
    today_iso = datetime.now(tz=UTC).date().isoformat()
    assert "attachment" in disposition
    assert "filename=" in disposition
    assert f"finsight-expenses-{today_iso}.csv" in disposition


async def test_export_header_row_matches_spec(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    first_line = response.text.splitlines()[0]
    assert first_line == EXPECTED_HEADER


async def test_export_handles_empty_result(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    assert len(rows) == 1
    assert ",".join(rows[0]) == EXPECTED_HEADER


# --- Scoping -----------------------------------------------------------------


async def test_export_returns_only_caller_expenses(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")

    await _create(client, a_headers, description="A's expense")
    await _create(client, b_headers, description="B's expense")

    response = await client.get("/export/csv", headers=a_headers)
    assert response.status_code == 200
    body = response.text
    assert "A's expense" in body
    assert "B's expense" not in body


# --- Ordering & rows ---------------------------------------------------------


async def test_export_one_row_per_expense_in_descending_date_order(
    client: AsyncClient,
) -> None:
    headers = await auth_headers(client)
    now = datetime.now(tz=UTC)
    await _create(
        client,
        headers,
        description="oldest",
        occurred_at=(now - timedelta(days=10)).isoformat(),
    )
    await _create(
        client,
        headers,
        description="middle",
        occurred_at=(now - timedelta(days=5)).isoformat(),
    )
    await _create(
        client,
        headers,
        description="newest",
        occurred_at=now.isoformat(),
    )

    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    # Header + 3 data rows
    assert len(rows) == 4
    descriptions = [r[2] for r in rows[1:]]
    assert descriptions == ["newest", "middle", "oldest"]


# --- Filters -----------------------------------------------------------------


async def test_export_filters_by_from_date(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    today = datetime.now(tz=UTC)
    await _create(
        client, headers, description="old", occurred_at=(today - timedelta(days=7)).isoformat()
    )
    await _create(
        client, headers, description="recent", occurred_at=(today - timedelta(days=1)).isoformat()
    )
    from_param = (today - timedelta(days=2)).date().isoformat()

    response = await client.get(f"/export/csv?from={from_param}", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    assert len(rows) == 2  # header + 1
    assert rows[1][2] == "recent"


async def test_export_filters_by_to_date(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    today = datetime.now(tz=UTC)
    await _create(
        client, headers, description="old", occurred_at=(today - timedelta(days=7)).isoformat()
    )
    await _create(
        client, headers, description="recent", occurred_at=(today - timedelta(days=1)).isoformat()
    )
    to_param = (today - timedelta(days=3)).date().isoformat()

    response = await client.get(f"/export/csv?to={to_param}", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    assert len(rows) == 2
    assert rows[1][2] == "old"


async def test_export_filters_by_category_id(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    first = await _create(client, headers, description="match-me")
    cat_id = first["category_id"]
    # Create another expense with same category id explicitly
    await _create(client, headers, description="also-match", category_id=cat_id)

    response = await client.get(f"/export/csv?category_id={cat_id}", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    # All data rows should match this category. Other expenses by other users
    # don't exist, but ensure all rows match this category — second to last col
    # is currency, last is source. category column index = 3.
    descriptions = [r[2] for r in rows[1:]]
    assert "match-me" in descriptions
    assert "also-match" in descriptions


async def test_export_invalid_from_date_returns_422(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv?from=not-a-date", headers=headers)
    assert response.status_code == 422


async def test_export_invalid_to_date_returns_422(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/export/csv?to=2026-13-99", headers=headers)
    assert response.status_code == 422


# --- RFC 4180 escaping -------------------------------------------------------


async def test_export_csv_escapes_commas_in_description(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    description = "Almuerzo, café y postre"
    await _create(client, headers, description=description)

    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    assert rows[1][2] == description


async def test_export_csv_escapes_quotes_in_description(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    description = 'He said "hola" today'
    await _create(client, headers, description=description)

    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    assert rows[1][2] == description


async def test_export_csv_escapes_newlines_in_description(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    description = "line1\nline2"
    await _create(client, headers, description=description)

    response = await client.get("/export/csv", headers=headers)
    assert response.status_code == 200
    rows = _parse_csv(response.text)
    # Header + 1 data row preserved through csv.reader despite embedded newline
    assert len(rows) == 2
    assert rows[1][2] == description


# --- Format details ----------------------------------------------------------


async def test_export_amount_format_is_plain_decimal(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    await _create(client, headers, amount="12.50", description="x")

    response = await client.get("/export/csv", headers=headers)
    rows = _parse_csv(response.text)
    # column indices: 0 id, 1 occurred_at, 2 description, 3 category,
    # 4 amount, 5 currency, 6 amount_base
    assert rows[1][4] == "12.50"
    assert rows[1][6] == "12.50"
    assert "$" not in response.text
    assert "12,50" not in response.text


async def test_export_occurred_at_iso_8601_utc(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    when = datetime(2026, 5, 8, 13, 42, 0, tzinfo=UTC)
    await _create(client, headers, description="x", occurred_at=when.isoformat())

    response = await client.get("/export/csv", headers=headers)
    rows = _parse_csv(response.text)
    occurred_at_str = rows[1][1]
    parsed = datetime.fromisoformat(occurred_at_str.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    # Convert to UTC and compare
    assert parsed.astimezone(UTC) == when


async def test_export_category_column_is_name_not_id(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await _create(client, headers, description="lunch")
    cat_id = created["category_id"]

    response = await client.get("/export/csv", headers=headers)
    rows = _parse_csv(response.text)
    category_value = rows[1][3]
    # Must NOT be the numeric id
    assert category_value != str(cat_id)
    # Must be a non-empty string from the seeded defaults
    assert category_value != ""
    known_names = {
        "Food",
        "Transport",
        "Housing",
        "Health",
        "Entertainment",
        "Education",
        "Shopping",
        "Bills",
        "Other",
    }
    assert category_value in known_names


# Marker import to satisfy pytest plugin if any test relies on markers later.
_ = pytest
