"""Render pages with CSRF protection on, as in production; the rest of the suite runs with it off."""

import io
import zipfile
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from _pytest.mark.structures import ParameterSet
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask_security.recoverable import generate_reset_password_token

from app.models import User
from tests.aliases import ClientFactory, SeedData
from tests.constants import EMAILS, TEST_PASSWORD
from tests.test_backup import _forbidden_build
from tests.test_smoke_pages import EXPECTED, ROLES, Bug, _resolve_params

CSRF_INPUT = 'name="csrf_token"'
CSRF_MESSAGE = "Esta página ficou aberta por muito tempo."


@pytest.fixture
def csrf_on(app: Flask, client_for: ClientFactory) -> Iterator[None]:
    """Turn CSRF protection on for one test and restore the test setting afterwards.

    Depends on client_for so the per-role logins happen before, with CSRF still off.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :return: Nothing; the fixture yields while CSRF protection is on.
    """
    previous = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    yield
    app.config["WTF_CSRF_ENABLED"] = previous


def _cases_without_known_bugs() -> Iterator[ParameterSet]:
    """Expand the smoke table into (row, role) params, leaving out the cells of known bugs.

    :return: A generator of pytest params with ids "<endpoint>[<label>]-<role>".
    """
    for item in EXPECTED:
        for role in ROLES:
            if not isinstance(item["expected"][role], Bug):
                yield pytest.param(item, role, id=f"{item['endpoint']}[{item['label']}]-{role}")


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize("item, role", list(_cases_without_known_bugs()))
def test_every_get_page_keeps_its_status_with_csrf(
    app: Flask, seed: SeedData, client_for: ClientFactory, item: dict[str, Any], role: str
) -> None:
    """Check that every GET page answers the same status with CSRF protection on.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param item: Row of the smoke expectations table.
    :param role: Role that requests the page.
    """
    with app.test_request_context():
        url = url_for(item["endpoint"], **_resolve_params(item["params"], seed))
    expected = item["expected"][role]
    expected_status = expected[0] if isinstance(expected, tuple) else expected

    response = client_for(role).get(url)

    assert response.status_code == expected_status, f"{role} GET {url}: {response.status_code} != {expected_status}"


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize(
    "role, endpoint",
    [
        ("anonymous", "security.login"),
        ("anonymous", "security.forgot_password"),
        ("admin", "security.change_password"),
        ("admin", "security.verify"),
    ],
)
def test_auth_forms_render_the_csrf_token(app: Flask, client_for: ClientFactory, role: str, endpoint: str) -> None:
    """Check that the auth forms render with their CSRF token.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param role: Role that requests the page.
    :param endpoint: Flask-Security endpoint of the form.
    """
    with app.test_request_context():
        url = url_for(endpoint)

    response = client_for(role).get(url)

    assert response.status_code == 200, f"{role} GET {url}: {response.status_code}"
    assert CSRF_INPUT in response.get_data(as_text=True)


@pytest.mark.usefixtures("csrf_on")
def test_reset_password_form_renders_the_csrf_token(app: Flask, client_for: ClientFactory) -> None:
    """Check that the reset password form opened from a valid token renders with its CSRF token.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    with app.test_request_context():
        user = User.query.filter_by(email=EMAILS["admin"]).one()
        url = url_for("security.reset_password", token=generate_reset_password_token(user))

    response = client_for("anonymous").get(url)

    assert response.status_code == 200
    assert CSRF_INPUT in response.get_data(as_text=True)


@pytest.mark.usefixtures("csrf_on")
def test_login_without_csrf_token_shows_the_session_message(client_for: ClientFactory) -> None:
    """Check that a login posted without CSRF token shows the pt-BR session message instead of failing.

    :param client_for: Factory of test clients by role.
    """
    response = client_for("anonymous").post("/login", data={"email": EMAILS["admin"], "password": TEST_PASSWORD})

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'role="alert"' in body
    assert CSRF_MESSAGE in body


@pytest.mark.usefixtures("csrf_on")
def test_backup_form_renders_the_csrf_token(
    app: Flask, client_for: ClientFactory, set_superusers: Callable[[str], None]
) -> None:
    """Check that the backup download form renders with its CSRF token.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    """
    set_superusers(EMAILS["admin"])
    with app.test_request_context():
        url = url_for("backup.show_backup")

    response = client_for("admin").get(url)

    assert response.status_code == 200
    assert CSRF_INPUT in response.get_data(as_text=True)


@pytest.mark.usefixtures("csrf_on")
def test_backup_download_is_refused_without_the_csrf_token(
    app: Flask, client_for: ClientFactory, set_superusers: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a download posted without the token builds nothing, and that the token of the page is accepted.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    :param monkeypatch: Pytest monkeypatch fixture.
    """
    set_superusers(EMAILS["admin"])
    with app.test_request_context():
        url = url_for("backup.show_backup")
    client = client_for("admin")

    with monkeypatch.context() as patch:
        patch.setattr("app.views.backup.build_backup", _forbidden_build)
        refused = client.post(url)
        wrong = client.post(url, data={"csrf_token": "not-a-valid-token"})
    page = client.get(url).get_data(as_text=True)
    token = BeautifulSoup(page, "html.parser").select_one("input[name=csrf_token]")["value"]
    accepted = client.post(url, data={"csrf_token": token})

    for response in (refused, wrong):
        assert response.status_code == 302
        assert response.headers["Location"] == url
        assert response.mimetype != "application/zip"
    assert accepted.status_code == 200 and accepted.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(accepted.data)) as archive:
        assert "manifest.json" in archive.namelist()
    assert "Atualize a página e tente novamente." in page
