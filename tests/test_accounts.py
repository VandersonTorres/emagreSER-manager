"""Accounts: self-registration is closed, and the staff still creates accounts in the users page."""

from collections.abc import Iterator
from urllib.parse import urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.models import User, db
from tests.aliases import ClientFactory
from tests.constants import TEST_PASSWORD

STRANGER_EMAIL = "estranho@test.local"
NEW_ACCOUNT_EMAIL = "nova.conta@test.local"
NEW_ACCOUNT_PASSWORD = "Nova-Conta-123!"  # pragma: allowlist secret


@pytest.fixture
def new_account_email(app: Flask) -> Iterator[str]:
    """Provide the e-mail of an account created by a test and delete that account afterwards.

    :param app: Flask application.
    :return: The e-mail (yielded; any account with it is deleted afterwards).
    """
    yield NEW_ACCOUNT_EMAIL
    with app.app_context():
        user = User.query.filter_by(email=NEW_ACCOUNT_EMAIL).first()
        if user is not None:
            db.session.delete(user)
            db.session.commit()


def test_self_registration_is_closed(app: Flask, client: FlaskClient) -> None:
    """Check that /register does not exist for GET nor POST and that a POST creates no account.

    :param app: Flask application.
    :param client: Anonymous test client.
    """
    form = {"email": STRANGER_EMAIL, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD}

    assert client.get("/register").status_code == 404
    assert client.post("/register", data=form).status_code == 404
    with app.app_context():
        assert User.query.filter_by(email=STRANGER_EMAIL).first() is None


def test_login_page_has_no_registration_link(client: FlaskClient) -> None:
    """Check that the login page does not point to a registration page.

    :param client: Anonymous test client.
    """
    html = client.get("/login").get_data(as_text=True)

    assert "/register" not in html


@pytest.mark.parametrize("role", ["admin", "secretary"])
def test_staff_still_creates_accounts_that_can_log_in(
    app: Flask, client_for: ClientFactory, new_account_email: str, role: str
) -> None:
    """Create an account in the users page with registration closed, then log in with it.

    :param app: Flask application.
    :param client_for: Factory of test clients per role.
    :param new_account_email: E-mail of the account to create.
    :param role: Role of the staff member who creates the account.
    """
    form = {"name": "Nova Conta", "email": new_account_email, "password": NEW_ACCOUNT_PASSWORD, "role": "secretary"}

    response = client_for(role).post("/admin/create_user", data=form)

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/users"
    with app.app_context():
        user = User.query.filter_by(email=new_account_email).one()
        assert user.active is True
        assert [item.name for item in user.roles] == ["secretary"]
    login = client_for("anonymous").post("/login", data={"email": new_account_email, "password": NEW_ACCOUNT_PASSWORD})
    assert login.status_code == 302
