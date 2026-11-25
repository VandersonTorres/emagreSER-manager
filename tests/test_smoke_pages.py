"""Smoke test of every GET page of the app, per role (anonymous, admin, secretary, nutritionist)."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, TypeAlias
from urllib.parse import urlparse

import pytest
from _pytest.mark.structures import ParameterSet
from flask import Flask, url_for

from tests.aliases import ClientFactory, SeedData

ANON, ADMIN, SECRETARY, NUTRITIONIST = "anonymous", "admin", "secretary", "nutritionist"
ROLES = (ANON, ADMIN, SECRETARY, NUTRITIONIST)

Cell: TypeAlias = int | tuple[int, str]


class ExistingBug(Exception):
    """Signal that a Bug cell still fails the known way (500); only this counts as an expected failure."""


@dataclass(frozen=True)
class Bug:
    """Table cell for a known bug: the correct status is `expected`, but the app currently answers 500.

    The test is xfail(strict=True, raises=ExistingBug): only a 500 raises ExistingBug. Any other status fails the test,
    and the correct status is a strict XPASS, so the table must be updated in both cases.

    :param expected: Cell the app should produce (a status or a (status, path) tuple).
    :param reason: Description of the bug.
    """

    expected: Cell
    reason: str


Expectation: TypeAlias = Cell | Bug


def row(
    label: str,
    endpoint: str,
    params: dict[str, int | str],
    anonymous: Expectation,
    admin: Expectation,
    secretary: Expectation,
    nutritionist: Expectation,
) -> dict[str, Any]:
    """Build one row of the expectations table.

    Each role cell is a status int, a (status, "/path") tuple for redirects (path of the Location header without
    query) or a Bug. Param values starting with "@" reference ids of the `seed` fixture.

    :param label: Short name of the row, used in the test id.
    :param endpoint: Flask endpoint name.
    :param params: Arguments passed to url_for.
    :param anonymous: Expected cell for an anonymous visitor.
    :param admin: Expected cell for the admin role.
    :param secretary: Expected cell for the secretary role.
    :param nutritionist: Expected cell for the nutritionist role.
    :return: The row dict.
    """
    return {
        "label": label,
        "endpoint": endpoint,
        "params": params,
        "expected": {ANON: anonymous, ADMIN: admin, SECRETARY: secretary, NUTRITIONIST: nutritionist},
    }


LOGIN = (302, "/login")
HOME = (302, "/")
PATIENT_LIST = (302, "/patients-manager/patients")
SPECIALIST_LIST = (302, "/specialists-manager/specialists")

EXPECTED: list[dict[str, Any]] = [
    row("home", "main.index", {}, LOGIN, 200, 200, 200),
    row("new-user", "admin.create_user", {}, 403, 200, 200, HOME),
    row("list", "admin.list_users", {}, 403, 200, 200, HOME),
    row("delete", "admin.delete_user", {"id": "@user_secretary"}, 403, 200, 200, HOME),
    row("list", "specialists.list_specialists", {}, 403, 200, 200, HOME),
    row("new", "specialists.add_specialist", {}, 403, 200, 200, SPECIALIST_LIST),
    row("edit", "specialists.edit_specialist", {"id": "@specialist_other"}, 403, 200, 200, SPECIALIST_LIST),
    row("list", "schedules.list_schedules", {}, 403, 200, 200, 200),
    row("list-by-date", "schedules.list_schedules", {"date": "@schedule_future_date"}, 403, 200, 200, 200),
    row("schedule", "schedules.schedule_action", {}, 403, 200, 200, 200),
    row("list", "patients.list_patients", {}, 403, 200, 200, 200),
    row("list-search", "patients.list_patients", {"search": "Teste 1"}, 403, 200, 200, 200),
    row("new", "patients.add_patient", {}, 403, 200, 200, 200),
    row("view-p1", "patients.view_patient", {"id": "@patient_nutritionist"}, 403, 200, 200, 200),
    row("view-p2", "patients.view_patient", {"id": "@patient_schedule"}, 403, 200, 200, 200),
    row("view-p3", "patients.view_patient", {"id": "@patient_other"}, 403, 200, 200, PATIENT_LIST),
    row("view-missing", "patients.view_patient", {"id": 999}, 403, 404, 404, 404),
    row("edit-p1", "patients.edit_patient", {"id": "@patient_nutritionist"}, 403, 200, 200, 200),
    row("edit-p2", "patients.edit_patient", {"id": "@patient_schedule"}, 403, 200, 200, 200),
    row("edit-p3", "patients.edit_patient", {"id": "@patient_other"}, 403, 200, 200, PATIENT_LIST),
    row("delete-p1", "patients.delete_patient", {"id": "@patient_nutritionist"}, 403, 200, 200, PATIENT_LIST),
    row("new-anthro-p1", "patients.add_anthro", {"patient_id": "@patient_nutritionist"}, 403, 200, 200, 200),
    row("new-anthro-p2", "patients.add_anthro", {"patient_id": "@patient_schedule"}, 403, 200, 200, 200),
    row("new-anthro-p3", "patients.add_anthro", {"patient_id": "@patient_other"}, 403, 200, 200, PATIENT_LIST),
    row(
        "edit-anthro",
        "patients.edit_anthro",
        {"patient_id": "@patient_nutritionist", "evaluation_id": "@anthro"},
        403,
        200,
        200,
        200,
    ),
    row("new-skinfold-p1", "patients.add_skinfold", {"patient_id": "@patient_nutritionist"}, 403, 200, 200, 200),
    row("new-skinfold-p2", "patients.add_skinfold", {"patient_id": "@patient_schedule"}, 403, 200, 200, 200),
    row("new-skinfold-p3", "patients.add_skinfold", {"patient_id": "@patient_other"}, 403, 200, 200, PATIENT_LIST),
    row(
        "edit-skinfold",
        "patients.edit_skinfold",
        {"patient_id": "@patient_nutritionist", "skinfold_id": "@skinfold"},
        403,
        200,
        200,
        200,
    ),
    row(
        "history-p1-with-evaluation",
        "patients.view_custom_history",
        {"id": "@patient_nutritionist", "pat_name": "Paciente Teste 1"},
        403,
        200,
        200,
        200,
    ),
    row(
        "history-p2-without-evaluation",
        "patients.view_custom_history",
        {"id": "@patient_schedule", "pat_name": "Paciente Teste 2"},
        403,
        200,
        200,
        200,
    ),
    row(
        "history-p3",
        "patients.view_custom_history",
        {"id": "@patient_other", "pat_name": "Paciente Teste 3"},
        403,
        200,
        200,
        PATIENT_LIST,
    ),
    row("list", "diets.list_diets", {}, 403, 200, 200, 200),
    row("list-search", "diets.list_diets", {"query": "Teste"}, 403, 200, 200, 200),
    row("new", "diets.add_diet", {}, 403, 200, 200, 200),
    row("view", "diets.view_diet", {"id": "@diet_a4"}, 403, 200, 200, 200),
    row("view-missing", "diets.view_diet", {"id": 999}, 403, 404, 404, 404),
    row("delete", "diets.delete_diet", {"id": "@diet_a4"}, 403, 200, 200, 200),
    row("edit-pdf", "diets.edit_diet", {"id": "@diet_a4"}, 403, 200, 200, 200),
    row("edit-raw", "diets.edit_diet_raw", {"id": "@diet_a4"}, 403, 200, 200, 200),
    row("last-edition-with-file", "diets.view_last_edition", {"id": "@diet_edited"}, 403, 200, 200, 200),
    row("last-edition-without-file", "diets.view_last_edition", {"id": "@diet_a4"}, 403, 200, 200, 200),
    row("temp-file", "diets.serve_temp_file", {"filename": "@diet_edited_file"}, 200, 200, 200, 200),
    row("download-temp", "diets.download_temp_diet", {"filename": "@diet_edited_file"}, 403, 200, 200, 200),
    row("show", "backup.show_backup", {}, LOGIN, 403, 403, 403),
    row("login", "security.login", {}, 200, HOME, HOME, HOME),
    row("change-password", "security.change_password", {}, LOGIN, 200, 200, 200),
    row("forgot-password", "security.forgot_password", {}, 200, HOME, HOME, HOME),
    row("register", "security.register", {}, 200, HOME, HOME, HOME),
    row("logout", "security.logout", {}, LOGIN, LOGIN, LOGIN, LOGIN),
]

EXCLUDED: set[str] = set()
APP_BLUEPRINTS = {"main", "admin", "backup", "schedules", "patients", "specialists", "diets"}


def _parametrized_cases() -> Iterator[ParameterSet]:
    """Expand the table into one pytest param per row and role, marking Bug cells as strict xfail.

    :return: A generator of pytest params (row, role) with ids "<endpoint>[<label>]-<role>".
    """
    for item in EXPECTED:
        for role in ROLES:
            expected = item["expected"][role]
            marks: list[pytest.MarkDecorator] = []
            if isinstance(expected, Bug):
                marks.append(pytest.mark.xfail(strict=True, raises=ExistingBug, reason=expected.reason))
            yield pytest.param(item, role, marks=marks, id=f"{item['endpoint']}[{item['label']}]-{role}")


def _resolve_params(params: dict[str, int | str], seed: SeedData) -> dict[str, int | str]:
    """Replace "@name" values by the matching seed ids.

    :param params: url_for arguments, where strings starting with "@" reference the seed.
    :param seed: Ids of the fake records.
    :return: The arguments with the seed ids filled in.
    """
    return {k: (seed[v[1:]] if isinstance(v, str) and v.startswith("@") else v) for k, v in params.items()}


@pytest.mark.parametrize("item, role", list(_parametrized_cases()))
def test_page_by_role(app: Flask, seed: SeedData, client_for: ClientFactory, item: dict[str, Any], role: str) -> None:
    """Check the status, redirect target and body of a GET page for one role.

    200 responses must contain "</html>" (PDFs only need the mimetype and the %PDF header). A Bug cell raises
    ExistingBug on a 500; any other response follows the normal checks against the correct status.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param item: Row of the expectations table.
    :param role: Role that requests the page.
    :raises ExistingBug: If a Bug cell answers 500 as known.
    """
    with app.test_request_context():
        url = url_for(item["endpoint"], **_resolve_params(item["params"], seed))

    expected = item["expected"][role]
    bug = isinstance(expected, Bug)
    if bug:
        expected = expected.expected
    expected_status, expected_location = expected if isinstance(expected, tuple) else (expected, None)

    response = client_for(role).get(url)

    if bug and response.status_code == 500:
        raise ExistingBug(f"{role} GET {url}: 500 (known bug)")
    assert response.status_code == expected_status, f"{role} GET {url}: {response.status_code} != {expected_status}"
    if expected_location is not None:
        assert urlparse(response.headers["Location"]).path == expected_location
    if expected_status == 200:
        if response.mimetype == "application/pdf":
            assert response.data.startswith(b"%PDF")
        else:
            assert "</html>" in response.get_data(as_text=True)


def test_table_covers_all_get_endpoints(app: Flask) -> None:
    """Check that no GET endpoint of the app blueprints is missing from the expectations table.

    :param app: Flask application.
    """
    in_table = {item["endpoint"] for item in EXPECTED}
    registered = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if "GET" in rule.methods and rule.endpoint.split(".")[0] in APP_BLUEPRINTS
    }
    assert registered - in_table - EXCLUDED == set(), "GET endpoint without a row in the expectations table"
    assert (in_table - registered) - {e for e in in_table if e.startswith("security.")} == set()
