"""Unit tests for CSV import normalization."""

from __future__ import annotations

from prospectiq.domain.import_normalization import (
    detect_column_mapping,
    duplicate_key,
    map_row_to_fields,
    normalize_domain,
    sanitize_csv_cell,
)


def test_sanitize_csv_formula_injection() -> None:
    assert sanitize_csv_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert sanitize_csv_cell("+cmd") == "'+cmd"
    assert sanitize_csv_cell("normal@example.com") == "normal@example.com"


def test_detect_apollo_style_headers() -> None:
    headers = [
        "First Name",
        "Last Name",
        "Email",
        "Email Status",
        "Title",
        "Company Name",
        "Website",
        "Company Domain",
        "# Employees",
    ]
    result = detect_column_mapping(headers)
    assert result.mapping["First Name"].value == "first_name"
    assert result.mapping["Email Status"].value == "email_status"
    assert result.mapping["Company Domain"].value == "company_domain"
    assert "Email Status" not in result.unmapped_headers


def test_email_status_is_not_email() -> None:
    row = {
        "Email": "jane@acme.test",
        "Email Status": "verified",
        "Company Name": "Acme",
        "Company Domain": "acme.test",
    }
    mapping = detect_column_mapping(list(row.keys())).mapping
    normalized = map_row_to_fields(row, mapping)
    assert normalized["email"] == "jane@acme.test"
    assert normalized["email_status"] == "verified"


def test_normalize_domain_from_website() -> None:
    assert normalize_domain("https://www.stripe.com/about") == "stripe.com"


def test_duplicate_key_prefers_email() -> None:
    normalized = {"email": "a@test.com", "company_domain": "test.com", "full_name": "A B"}
    assert duplicate_key(normalized) == "email:a@test.com"
