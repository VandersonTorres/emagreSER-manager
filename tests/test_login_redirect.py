"""Redirect of unauthenticated visitors to the login page."""

from urllib.parse import parse_qs, urlparse

import pytest

from tests.aliases import ClientFactory
from tests.constants import EMAILS, TEST_PASSWORD

TOAST_MARKER = "app-toast"


@pytest.mark.parametrize("path", ["/", "/change"])
def test_visitor_goes_to_login_without_alert(client_for: ClientFactory, path: str) -> None:
    """Check that a visitor is sent to the login page with ``next`` and that no alert is shown there.

    :param client_for: Factory of test clients by role.
    :param path: Page that requires a login.
    """
    client = client_for("anonymous")

    response = client.get(path)

    location = urlparse(response.headers["Location"])
    assert response.status_code == 302
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == [path]
    login_page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert TOAST_MARKER not in login_page


def test_home_after_login_shows_no_stale_alert(client_for: ClientFactory) -> None:
    """Check that logging in after the redirect lands on a home page without a leftover alert.

    :param client_for: Factory of test clients by role.
    """
    client = client_for("anonymous")
    client.get("/")

    login = client.post("/login?next=/", data={"email": EMAILS["admin"], "password": TEST_PASSWORD})
    home = client.get("/").get_data(as_text=True)

    assert login.status_code == 302
    assert TOAST_MARKER not in home


def test_json_request_keeps_the_401_answer(client_for: ClientFactory) -> None:
    """Check that a JSON client still gets the Flask-Security 401 instead of a redirect.

    :param client_for: Factory of test clients by role.
    """
    response = client_for("anonymous").get("/", headers={"Accept": "application/json"})

    assert response.status_code == 401
