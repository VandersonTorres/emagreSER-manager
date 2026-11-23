"""Tests of the application shell: flash toasts, role-aware menu, home dashboard, auth pages and error pages."""

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from flask import Flask, flash, render_template, url_for
from flask.testing import FlaskClient
from flask_login import login_user
from flask_security.core import _default_messages

from app.dashboard import UPCOMING_LIMIT, format_when, local_now, upcoming_schedules
from app.models import Schedules, Specialists, User, db
from app.navigation import NAV_ITEMS, NavItem, build_navigation, visible_items
from config import Config
from tests.aliases import ClientFactory, SeedData
from tests.constants import EMAILS, NUTRITIONIST_USERNAME, TEST_PASSWORD

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"
LAYOUT_FILES = ("base.html", "_head_assets.html", "_topbar.html", "_sidebar.html", "_flash_toasts.html")
FORBIDDEN_MESSAGE = "Acesso negado! Você não tem permissão para acessar essa seção."
MANAGEMENT_ENDPOINTS = ("specialists.list_specialists", "admin.list_users")
OTHER_SPECIALIST = "Profissional Teste 2"
WRONG_PASSWORD = "wrong-password"  # pragma: allowlist secret
PLACEHOLDER = re.compile(r"%\((\w+)\)s")


def _soup(html: str) -> BeautifulSoup:
    """Parse an HTML document.

    :param html: HTML text.
    :return: The parsed document.
    """
    return BeautifulSoup(html, "html.parser")


def _sidebar_hrefs(html: str) -> list[str]:
    """List the targets of the sidebar links of a page.

    :param html: HTML text of a page rendered inside the application shell.
    :return: The href of every link inside the sidebar navigation.
    """
    return [link["href"] for link in _soup(html).select("#app-sidebar nav a")]


def _toast_texts(html: str) -> list[str]:
    """List the messages rendered inside the toast region.

    :param html: HTML text of a page.
    :return: The stripped text of every toast body in the region.
    """
    return [body.get_text().strip() for body in _soup(html).select("#toast-region .toast .toast-body")]


def _url(app: Flask, endpoint: str, **values: int | str) -> str:
    """Build a URL outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


@pytest.fixture
def extra_schedules(app: Flask, seed: SeedData) -> Iterator[dict[str, int]]:
    """Create temporary schedules and remove them after the test.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The ids of the created schedules, keyed by a short name (yielded; they are deleted afterwards).
    """
    now = local_now()
    base = now.replace(hour=9, minute=0, second=0, microsecond=0)
    nutritionist_patient = int(seed["patient_nutritionist"])
    other_patient = int(seed["patient_other"])
    rows = {
        "nutritionist_soon": Schedules(
            patient_id=nutritionist_patient,
            date_time=base + timedelta(days=1),
            specialist=NUTRITIONIST_USERNAME,
            status="pendente",
        ),
        "other_future": Schedules(
            patient_id=other_patient,
            date_time=base + timedelta(days=3),
            specialist=OTHER_SPECIALIST,
            status="pendente",
        ),
        "finished_future": Schedules(
            patient_id=other_patient,
            date_time=base + timedelta(days=2),
            specialist=OTHER_SPECIALIST,
            status="finalizado",
        ),
        "expired_pending": Schedules(
            patient_id=nutritionist_patient,
            date_time=base - timedelta(days=2),
            specialist=NUTRITIONIST_USERNAME,
            status="pendente",
        ),
    }
    with app.app_context():
        db.session.add_all(rows.values())
        db.session.commit()
        ids = {name: row.id for name, row in rows.items()}
    yield ids
    with app.app_context():
        Schedules.query.filter(Schedules.id.in_(ids.values())).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize(
    "category, kind, role, live",
    [
        ("success", "success", "status", "polite"),
        ("danger", "danger", "alert", "assertive"),
        ("error", "danger", "alert", "assertive"),
        ("warning", "warning", "status", "polite"),
        ("info", "info", "status", "polite"),
        ("message", "info", "status", "polite"),
        ("unexpected", "info", "status", "polite"),
    ],
)
def test_flash_category_mapping(app: Flask, category: str, kind: str, role: str, live: str) -> None:
    """Check the toast kind, ARIA role and visibility rendered for each flash category.

    :param app: Flask application.
    :param category: Flash category.
    :param kind: Expected toast kind.
    :param role: Expected ARIA role.
    :param live: Expected aria-live value.
    """
    with app.test_request_context():
        flash("Mensagem de teste", category)
        html = render_template("_flash_toasts.html")

    toast = _soup(html).select_one("#toast-region .toast")
    assert toast is not None
    assert f"app-toast-{kind}" in toast["class"]
    assert "show" in toast["class"]
    assert toast["role"] == role
    assert toast["aria-live"] == live
    assert toast["data-autohide"] == ("false" if kind == "danger" else "true")


def test_flash_message_is_escaped(app: Flask) -> None:
    """Check that a flashed message cannot inject markup.

    :param app: Flask application.
    """
    with app.test_request_context():
        flash("<b>negrito</b>", "info")
        html = render_template("_flash_toasts.html")

    assert "&lt;b&gt;negrito&lt;/b&gt;" in html
    assert "<b>negrito</b>" not in html


def test_flash_message_renders_once_inside_toast_region(client_nutritionist: FlaskClient) -> None:
    """Check that a flashed message shows up exactly once, in the toast region, after a redirect.

    :param client_nutritionist: Test client logged in as nutritionist.
    """
    response = client_nutritionist.get("/specialists-manager/specialists", follow_redirects=True)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert html.count(FORBIDDEN_MESSAGE) == 1
    assert _toast_texts(html) == [FORBIDDEN_MESSAGE]
    toast = _soup(html).select_one("#toast-region .toast")
    assert toast is not None and toast["role"] == "alert"


def test_flash_message_is_consumed_by_the_first_page(client_nutritionist: FlaskClient) -> None:
    """Check that the message does not come back on the next page.

    :param client_nutritionist: Test client logged in as nutritionist.
    """
    client_nutritionist.get("/specialists-manager/specialists", follow_redirects=True)

    html = client_nutritionist.get("/").get_data(as_text=True)

    assert FORBIDDEN_MESSAGE not in html


@pytest.mark.parametrize("role", ["admin", "secretary"])
def test_management_roles_see_the_management_menu(app: Flask, client_for: ClientFactory, role: str) -> None:
    """Check that admin and secretary link to the specialists and users pages in the sidebar and on the home.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param role: Role under test.
    """
    html = client_for(role).get("/").get_data(as_text=True)

    for endpoint in MANAGEMENT_ENDPOINTS:
        assert f'href="{_url(app, endpoint)}"' in html
        assert _url(app, endpoint) in _sidebar_hrefs(html)


def test_nutritionist_does_not_see_the_management_menu(app: Flask, client_nutritionist: FlaskClient) -> None:
    """Check that no page of the nutritionist links to the specialists or users pages.

    :param app: Flask application.
    :param client_nutritionist: Test client logged in as nutritionist.
    """
    pages = [
        client_nutritionist.get("/").get_data(as_text=True),
        client_nutritionist.get(_url(app, "patients.list_patients")).get_data(as_text=True),
        client_nutritionist.get(_url(app, "schedules.list_schedules")).get_data(as_text=True),
    ]

    for html in pages:
        for endpoint in MANAGEMENT_ENDPOINTS:
            assert f'href="{_url(app, endpoint)}"' not in html


@pytest.mark.parametrize(
    "endpoint, label",
    [
        ("main.index", "Início"),
        ("patients.view_patient", "Pacientes"),
        ("patients.list_patients", "Pacientes"),
        ("diets.edit_diet", "Dietas"),
        ("specialists.add_specialist", "Profissionais"),
        ("admin.create_user", "Usuários"),
        ("schedules.schedule_action", "Agendar consulta"),
        ("schedules.list_schedules", "Agenda"),
        ("schedules.delete_schedule", "Agenda"),
        ("security.change_password", None),
        (None, None),
    ],
)
def test_active_navigation_item(app: Flask, endpoint: str | None, label: str | None) -> None:
    """Check which sidebar entry is highlighted for an endpoint.

    :param app: Flask application.
    :param endpoint: Current endpoint, or None when no route matched.
    :param label: Label of the entry expected to be active, or None.
    """
    with app.test_request_context():
        links = build_navigation(["admin"], endpoint)

    assert [link.label for link in links if link.active] == ([label] if label else [])


def test_active_item_is_marked_in_the_page(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the rendered sidebar marks exactly the current entry with aria-current.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get(_url(app, "patients.list_patients")).get_data(as_text=True)

    current = _soup(html).select("#app-sidebar a[aria-current='page']")
    assert [link.get_text().strip() for link in current] == ["Pacientes"]


def test_nav_labels_by_role() -> None:
    """Check the entries and the order of each role, and that a new restricted entry is a single declaration."""
    nutritionist = [item.label for item in visible_items(["nutritionist"])]
    admin = [item.label for item in visible_items(["admin"])]
    secretary = [item.label for item in visible_items(["secretary"])]

    assert nutritionist == ["Início", "Pacientes", "Agenda", "Agendar consulta", "Dietas"]
    assert admin == secretary == [item.label for item in NAV_ITEMS]
    assert admin[-2:] == ["Profissionais", "Usuários"]

    restricted = NAV_ITEMS + (NavItem("Teste", "main.index", "bug", ("main.index",), roles=frozenset({"admin"})),)
    assert "Teste" in [item.label for item in visible_items(["admin"], restricted)]
    assert "Teste" not in [item.label for item in visible_items(["secretary"], restricted)]


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_home_has_no_form_nor_input(client_for: ClientFactory, role: str) -> None:
    """Check that the home page of every role has no form or input, so page scripts never bind to the layout.

    :param client_for: Factory of test clients by role.
    :param role: Role under test.
    """
    html = client_for(role).get("/").get_data(as_text=True).lower()

    assert "<form" not in html
    assert "<input" not in html


@pytest.mark.parametrize("name", LAYOUT_FILES)
def test_layout_files_have_no_form_nor_input(name: str) -> None:
    """Check that the layout sources never declare a form or an input.

    :param name: File name inside the templates folder.
    """
    source = (TEMPLATES_DIR / name).read_text(encoding="utf-8").lower()

    assert "<form" not in source
    assert "<input" not in source


def test_head_assets_are_pinned_with_integrity(client_admin: FlaskClient) -> None:
    """Check that every CDN asset of the page is pinned to a version and carries an SRI hash.

    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get("/").get_data(as_text=True))

    tags = soup.select("link[rel=stylesheet], script[src]")
    assets = [tag.get("href") or tag["src"] for tag in tags]
    external = [tag for tag, asset in zip(tags, assets) if asset.startswith("https://")]
    assert any("bootstrap@5.3.3" in asset for asset in assets)
    assert any("jquery-3.6.0" in asset for asset in assets)
    assert len(external) >= 6
    for tag in external:
        assert tag["integrity"].startswith("sha384-")
        assert tag["crossorigin"] == "anonymous"


def test_layout_skeleton(client_admin: FlaskClient) -> None:
    """Check the language, skip link, drawer markup and toast region of the shell.

    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get("/").get_data(as_text=True))

    assert soup.html["lang"] == "pt-BR"
    assert soup.select_one("a.skip-link[href='#main-content']").get_text().strip() == "Pular para o conteúdo"
    sidebar = soup.select_one("#app-sidebar")
    assert {"offcanvas-lg", "offcanvas-start"} <= set(sidebar["class"])
    toggle = soup.select_one("button[data-bs-target='#app-sidebar'][data-bs-toggle='offcanvas']")
    assert toggle["aria-label"] and "d-lg-none" in toggle["class"]
    assert soup.select_one("#app-sidebar .btn-close")["aria-label"]
    assert soup.select_one("#toast-region") is not None
    assert soup.select_one("#main-content .app-content.compat") is None


def test_head_order(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the order of the head: metas, title, stylesheets, scripts, select2 defaults and the page head block.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get(_url(app, "diets.view_diet", id=int(seed["diet_a4"]))).get_data(as_text=True)

    markers = [
        '<meta charset="utf-8">',
        'name="viewport"',
        'name="theme-color"',
        "<title>",
        "bootstrap@5.3.3/dist/css/bootstrap.min.css",
        "bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        "select2@4.1.0-rc.0/dist/css/select2.min.css",
        "select2-bootstrap-5-theme@1.3.0/dist/select2-bootstrap-5-theme.min.css",
        "css/app.css",
        "jquery-3.6.0.min.js",
        "select2@4.1.0-rc.0/dist/js/select2.min.js",
        'defaults.set("theme", "bootstrap-5")',
        'defaults.set("width", "100%")',
        "css/pdf_viewer.css",
        "</head>",
    ]
    positions = [html.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_user_menu_links(app: Flask, client_admin: FlaskClient) -> None:
    """Check the change password and logout links of the user menu.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get("/").get_data(as_text=True))

    menu = {link.get_text().strip(): link["href"] for link in soup.select(".dropdown-menu a.dropdown-item")}
    assert menu["Trocar senha"] == _url(app, "security.change_password")
    assert menu["Sair"] == _url(app, "security.logout")
    assert EMAILS["admin"] in soup.select_one(".dropdown-menu").get_text()


def test_compat_wrapper_only_on_pages_not_redesigned(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the home does not use the compatibility wrapper and a legacy page does.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    home = _soup(client_admin.get("/").get_data(as_text=True))
    patients = _soup(client_admin.get(_url(app, "patients.list_patients")).get_data(as_text=True))

    assert home.select_one(".app-content.compat") is None
    assert home.select_one(".app-content") is not None
    assert patients.select_one(".app-content.compat") is not None


def test_login_page(app: Flask, client: FlaskClient) -> None:
    """Check the login page markup that the e2e login helper and the users rely on.

    :param app: Flask application.
    :param client: Anonymous test client.
    """
    response = client.get("/login")

    html = response.get_data(as_text=True)
    soup = _soup(html)
    form = soup.select_one("form.login-form")
    assert response.status_code == 200
    assert form is not None
    assert form.select_one("input[name=email][autocomplete=username][inputmode=email]") is not None
    assert form.select_one("input[name=password][autocomplete=current-password]") is not None
    assert form.select_one("input[name=remember][type=checkbox]") is not None
    assert [button.get_text().strip() for button in form.select("button[type=submit]")] == ["Entrar"]
    assert soup.select_one("#app-sidebar") is None
    assert soup.select_one(".brand-logo img[alt=EmagreSER]") is not None
    assert (
        "Este é um software de gerenciamento interno. Ainda não tem uma conta cadastrada? Solicite ao administrador"
        in html
    )
    assert soup.find("a", string="Esqueci minha senha")["href"] == _url(app, "security.forgot_password")


def test_login_keeps_next_in_the_form_action(client: FlaskClient) -> None:
    """Check that the login form posts to the same URL it was opened from, including the next argument.

    :param client: Anonymous test client.
    """
    html = client.get("/login?next=/patients-manager/patients").get_data(as_text=True)

    form = _soup(html).select_one("form.login-form")
    assert form["action"].endswith("/login?next=/patients-manager/patients")


def test_login_errors_are_shown_next_to_the_field(client: FlaskClient) -> None:
    """Check that a wrong password is reported inside the password field block.

    :param client: Anonymous test client.
    """
    response = client.post("/login", data={"email": EMAILS["admin"], "password": WRONG_PASSWORD})

    soup = _soup(response.get_data(as_text=True))
    feedback = soup.select_one("#password-feedback")
    assert response.status_code == 200
    assert feedback is not None and "Senha inválida, tente novamente" in feedback.get_text()
    assert "is-invalid" in soup.select_one("input[name=password]")["class"]
    assert soup.select_one("input[name=password]")["aria-describedby"] == "password-feedback"


def test_forgot_password_page(app: Flask, client: FlaskClient) -> None:
    """Check the forgot password page.

    :param app: Flask application.
    :param client: Anonymous test client.
    """
    response = client.get(_url(app, "security.forgot_password"))

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert soup.select_one("form input[name=email]") is not None
    assert soup.select_one("form button[type=submit]").get_text().strip() == "Enviar instruções"


def test_change_password_page(client_admin: FlaskClient) -> None:
    """Check the labels, autocomplete hints and button of the change password page.

    :param client_admin: Test client logged in as admin.
    """
    response = client_admin.get("/change")

    soup = _soup(response.get_data(as_text=True))
    labels = {label["for"]: label.get_text().strip() for label in soup.select("form label")}
    assert response.status_code == 200
    assert list(labels) == ["password", "new_password", "new_password_confirm"]
    assert list(labels.values()) == ["Senha atual", "Nova senha", "Confirmar nova senha"]
    assert soup.select_one("input[name=password]")["autocomplete"] == "current-password"
    assert soup.select_one("input[name=new_password]")["autocomplete"] == "new-password"
    assert soup.select_one("input[name=new_password_confirm]")["autocomplete"] == "new-password"
    assert soup.select_one("form button[type=submit]").get_text().strip() == "Alterar senha"
    assert soup.select_one("#app-sidebar") is not None


def test_change_password_errors_are_shown_next_to_the_fields(client_admin: FlaskClient) -> None:
    """Check that validation errors of the change password form appear next to each field.

    :param client_admin: Test client logged in as admin.
    """
    mismatch = client_admin.post(
        "/change",
        data={
            "password": WRONG_PASSWORD,
            "new_password": "Another-pass-123",  # pragma: allowlist secret
            "new_password_confirm": "Different-pass-123",  # pragma: allowlist secret
        },
    )
    wrong_current = client_admin.post(
        "/change",
        data={
            "password": WRONG_PASSWORD,
            "new_password": "Another-pass-123",  # pragma: allowlist secret
            "new_password_confirm": "Another-pass-123",  # pragma: allowlist secret
        },
    )

    mismatch_soup = _soup(mismatch.get_data(as_text=True))
    current_soup = _soup(wrong_current.get_data(as_text=True))
    assert mismatch.status_code == wrong_current.status_code == 200
    assert "As senhas não conferem." in mismatch_soup.select_one("#new_password_confirm-feedback").get_text()
    assert "is-invalid" in mismatch_soup.select_one("input[name=new_password_confirm]")["class"]
    assert "Senha inválida, tente novamente" in current_soup.select_one("#password-feedback").get_text()


def test_unknown_url_renders_the_custom_404(client: FlaskClient, client_admin: FlaskClient) -> None:
    """Check the custom 404 page for a visitor and for a logged in user, keeping the status code.

    :param client: Anonymous test client.
    :param client_admin: Test client logged in as admin.
    """
    visitor = client.get("/this-page-does-not-exist")
    member = client_admin.get("/this-page-does-not-exist")

    assert visitor.status_code == member.status_code == 404
    visitor_soup = _soup(visitor.get_data(as_text=True))
    member_soup = _soup(member.get_data(as_text=True))
    assert visitor_soup.select_one(".error-page-title").get_text() == "Página não encontrada"
    assert visitor_soup.select_one("#app-sidebar") is None
    assert visitor_soup.find("a", string="Entrar") is not None
    assert member_soup.select_one(".error-page-title").get_text() == "Página não encontrada"
    assert member_soup.select_one("#app-sidebar") is not None
    assert member_soup.find("a", string="Voltar ao início")["href"] == "/"


def test_anonymous_protected_page_renders_the_custom_403(app: Flask, client: FlaskClient) -> None:
    """Check that a visitor opening a protected page gets the custom 403 with a link to the login page.

    :param app: Flask application.
    :param client: Anonymous test client.
    """
    path = _url(app, "patients.list_patients")

    response = client.get(path)

    soup = _soup(response.get_data(as_text=True))
    login_link = soup.find("a", string="Entrar")
    assert response.status_code == 403
    assert soup.select_one(".error-page-title").get_text() == "Acesso negado"
    assert login_link is not None
    assert login_link["href"].startswith(_url(app, "security.login"))
    assert soup.select_one("#app-sidebar") is None


def test_forbidden_page_for_a_logged_in_user_leads_home(app: Flask, seed: SeedData) -> None:
    """Check the 403 page of a logged in user: no login button, a way back to the home and the application shell.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/restricted"):
        login_user(db.session.get(User, int(seed["user_nutritionist"])))
        html = render_template("errors/403.html")

    soup = _soup(html)
    assert soup.find("a", string="Entrar") is None
    assert soup.find("a", string="Voltar ao início")["href"] == "/"
    assert soup.select_one("#app-sidebar") is not None


def test_server_error_page_is_self_contained(
    app: Flask, client_admin: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check the 500 page: custom, same status code, and rendered without user, navigation or sidebar.

    The home view is forced to fail and the navigation builder is made to fail if it is ever called, which proves
    that the error page skips the context processors.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param monkeypatch: Pytest monkeypatch fixture.
    """

    def explode(*args: object, **kwargs: object) -> None:
        """Fail like a view hitting a broken database.

        :param args: Ignored positional arguments.
        :param kwargs: Ignored keyword arguments.
        :raises RuntimeError: Always.
        """
        raise RuntimeError("database is gone")

    def forbidden_navigation(*args: object, **kwargs: object) -> None:
        """Fail if the navigation is built while the error page renders.

        :param args: Ignored positional arguments.
        :param kwargs: Ignored keyword arguments.
        :raises AssertionError: Always.
        """
        raise AssertionError("the error page must not build the navigation")

    monkeypatch.setattr("app.views.main.upcoming_schedules", explode)
    monkeypatch.setattr("app.navigation.build_navigation", forbidden_navigation)

    response = client_admin.get("/")

    html = response.get_data(as_text=True)
    soup = _soup(html)
    assert response.status_code == 500
    assert soup.select_one(".error-page-title").get_text() == "Algo deu errado"
    assert soup.select_one("#app-sidebar") is None
    assert soup.select_one(".app-topbar") is None
    assert "Usuario Teste admin" not in html
    assert EMAILS["admin"] not in html
    assert "database is gone" not in html


@pytest.mark.parametrize("key", [name for name in vars(Config) if name.startswith("SECURITY_MSG_")])
def test_security_messages_match_the_default_placeholders(key: str) -> None:
    """Check that each translated Flask-Security message targets a real key and keeps the default placeholders.

    :param key: Name of the config attribute (SECURITY_MSG_<KEY>).
    """
    default_key = key.removeprefix("SECURITY_MSG_")

    text, category = getattr(Config, key)

    assert default_key in _default_messages, f"{default_key} is not a Flask-Security message"
    assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(str(_default_messages[default_key][0])))
    assert category in {"success", "info", "warning", "error"}


def test_main_security_messages_are_translated() -> None:
    """Check that the main messages of the spec are configured."""
    required = {
        "LOGIN",
        "UNAUTHORIZED",
        "INVALID_PASSWORD",
        "USER_DOES_NOT_EXIST",
        "DISABLED_ACCOUNT",
        "PASSWORD_NOT_PROVIDED",
        "EMAIL_NOT_PROVIDED",
        "INVALID_EMAIL_ADDRESS",
        "PASSWORD_INVALID_LENGTH",
        "PASSWORD_IS_THE_SAME",
        "RETYPE_PASSWORD_MISMATCH",
        "PASSWORD_CHANGE",
        "PASSWORD_RESET_REQUEST",
        "PASSWORD_RESET",
        "INVALID_RESET_PASSWORD_TOKEN",
        "PASSWORD_RESET_EXPIRED",
        "REAUTHENTICATION_REQUIRED",
        "REAUTHENTICATION_SUCCESSFUL",
        "GENERIC_AUTHN_FAILED",
    }

    configured = {name.removeprefix("SECURITY_MSG_") for name in vars(Config) if name.startswith("SECURITY_MSG_")}

    assert required <= configured


@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2026, 11, 25, 14, 30), "qua, 25/11 · 14:30"),
        (datetime(2026, 11, 22, 8, 5), "dom, 22/11 · 08:05"),
        (datetime(2026, 11, 28, 23, 59), "sáb, 28/11 · 23:59"),
    ],
)
def test_format_when_does_not_depend_on_the_locale(moment: datetime, expected: str) -> None:
    """Check the pt-BR weekday, date and time label.

    :param moment: Moment to format.
    :param expected: Expected label.
    """
    assert format_when(moment) == expected


def test_home_shows_only_the_own_upcoming_schedules_to_the_nutritionist(
    client_nutritionist: FlaskClient, extra_schedules: dict[str, int]
) -> None:
    """Check that the nutritionist sees pending schedules of their own, ascending, and nothing from others.

    :param client_nutritionist: Test client logged in as nutritionist.
    :param extra_schedules: Ids of the temporary schedules.
    """
    html = client_nutritionist.get("/").get_data(as_text=True)

    items = _soup(html).select(".upcoming-item")
    names = [item.select_one(".upcoming-body a").get_text().strip() for item in items]
    assert names == ["Paciente Teste 1", "Paciente Teste 2"]
    assert OTHER_SPECIALIST not in html
    assert "Paciente Teste 3" not in html
    assert not any(item.select_one("small") for item in items)


def test_home_shows_every_upcoming_schedule_to_the_admin(
    client_admin: FlaskClient, extra_schedules: dict[str, int]
) -> None:
    """Check that the admin sees every pending future schedule with the specialist name.

    :param client_admin: Test client logged in as admin.
    :param extra_schedules: Ids of the temporary schedules.
    """
    html = client_admin.get("/").get_data(as_text=True)

    items = _soup(html).select(".upcoming-item")
    rows = [
        (
            item.select_one(".upcoming-body a").get_text().strip(),
            item.select_one(".upcoming-body small").get_text().strip(),
        )
        for item in items
    ]
    assert rows == [
        ("Paciente Teste 1", NUTRITIONIST_USERNAME),
        ("Paciente Teste 3", OTHER_SPECIALIST),
        ("Paciente Teste 2", NUTRITIONIST_USERNAME),
    ]
    assert _soup(html).find("a", string="Ver agenda completa") is not None


def test_home_limits_the_upcoming_list(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that the home lists at most the configured number of schedules.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    base = local_now().replace(hour=7, minute=0, second=0, microsecond=0)
    rows = [
        Schedules(
            patient_id=int(seed["patient_other"]),
            date_time=base + timedelta(days=1, minutes=10 * index),
            specialist=OTHER_SPECIALIST,
            status="pendente",
        )
        for index in range(UPCOMING_LIMIT + 2)
    ]
    with app.app_context():
        db.session.add_all(rows)
        db.session.commit()
        ids = [row.id for row in rows]
    try:
        html = client_admin.get("/").get_data(as_text=True)
    finally:
        with app.app_context():
            Schedules.query.filter(Schedules.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()

    assert len(_soup(html).select(".upcoming-item")) == UPCOMING_LIMIT


def test_home_without_specialist_row_shows_the_empty_state(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check the empty state for a nutritionist whose e-mail has no professional record.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as nutritionist.
    """
    with app.app_context():
        specialist = db.session.get(Specialists, int(seed["specialist_nutritionist"]))
        original = specialist.email
        specialist.email = "someone.else@test.local"
        db.session.commit()
    try:
        html = client_nutritionist.get("/").get_data(as_text=True)
    finally:
        with app.app_context():
            db.session.get(Specialists, int(seed["specialist_nutritionist"])).email = original
            db.session.commit()

    soup = _soup(html)
    assert soup.select(".upcoming-item") == []
    assert soup.select_one(".empty-state") is not None
    assert "Nenhuma consulta pendente" in html


def test_home_does_not_update_expired_schedules(
    app: Flask, client_admin: FlaskClient, client_nutritionist: FlaskClient, extra_schedules: dict[str, int]
) -> None:
    """Check that opening the home never writes: an expired pending schedule stays pending.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param client_nutritionist: Test client logged in as nutritionist.
    :param extra_schedules: Ids of the temporary schedules.
    """
    client_admin.get("/")
    client_nutritionist.get("/")

    with app.app_context():
        schedule = db.session.get(Schedules, extra_schedules["expired_pending"])
        assert schedule.status == "pendente"


def test_upcoming_schedules_ignores_past_and_finished(
    app: Flask, seed: SeedData, extra_schedules: dict[str, int]
) -> None:
    """Check the query rules: pending only, from the reference moment on, ascending.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param extra_schedules: Ids of the temporary schedules.
    """
    with app.app_context():
        admin = db.session.get(User, int(seed["user_admin"]))
        everything = upcoming_schedules(admin)
        later = upcoming_schedules(admin, now=local_now() + timedelta(days=5))

    assert [item.patient_name for item in everything] == ["Paciente Teste 1", "Paciente Teste 3", "Paciente Teste 2"]
    assert [item.patient_name for item in later] == ["Paciente Teste 2"]


def test_admin_card_only_for_management_roles(app: Flask, client_for: ClientFactory) -> None:
    """Check the administration card of the home and its two links.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    for role in ("admin", "secretary"):
        soup = _soup(client_for(role).get("/").get_data(as_text=True))
        card = soup.select_one("section[aria-labelledby=admin-title]")
        assert card is not None
        assert [link["href"] for link in card.select("a")] == [
            _url(app, "admin.list_users"),
            _url(app, "admin.create_user"),
        ]

    nutritionist = _soup(client_for("nutritionist").get("/").get_data(as_text=True))
    assert nutritionist.select_one("section[aria-labelledby=admin-title]") is None


def test_home_shortcuts_and_greeting(app: Flask, client_admin: FlaskClient) -> None:
    """Check the greeting and the four shortcuts of the home.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get("/").get_data(as_text=True))

    assert soup.select_one(".page-header-title").get_text() == "Olá, Usuario Teste admin"
    shortcuts = {tile.get_text().strip(): tile["href"] for tile in soup.select("a.shortcut-tile")}
    assert shortcuts == {
        "Novo paciente": _url(app, "patients.add_patient"),
        "Agendar consulta": _url(app, "schedules.schedule_action"),
        "Agenda": _url(app, "schedules.list_schedules"),
        "Dietas": _url(app, "diets.list_diets"),
    }


def test_home_greets_with_the_email_when_there_is_no_username(
    app: Flask, seed: SeedData, client_secretary: FlaskClient
) -> None:
    """Check the greeting fallback to the e-mail.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_secretary: Test client logged in as secretary.
    """
    with app.app_context():
        user = db.session.get(User, int(seed["user_secretary"]))
        original = user.username
        user.username = None
        db.session.commit()
    try:
        html = client_secretary.get("/").get_data(as_text=True)
    finally:
        with app.app_context():
            db.session.get(User, int(seed["user_secretary"])).username = original
            db.session.commit()

    assert _soup(html).select_one(".page-header-title").get_text() == f"Olá, {EMAILS['secretary']}"


def test_home_has_no_slider(client_admin: FlaskClient) -> None:
    """Check that the unpinned slider library is gone from the home page.

    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get("/").get_data(as_text=True)

    assert "swiper" not in html.lower()
    assert "unpkg.com" not in html


def test_previous_editor_keeps_the_legacy_stylesheet(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that the previous diet editor ("?legacy=1") loads the legacy stylesheet and none of the new framework.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get(_url(app, "diets.edit_diet", id=int(seed["diet_a4"]), legacy=1)).get_data(as_text=True)

    assert "css/legacy.css" in html
    assert "css/app.css" not in html
    assert "bootstrap" not in html.lower()
    assert "app-topbar" not in html


def test_legacy_stylesheet_is_a_byte_copy_of_style_css() -> None:
    """Check that legacy.css is byte-identical to style.css."""
    css_dir = TEMPLATES_DIR.parent / "static" / "css"

    assert (css_dir / "legacy.css").read_bytes() == (css_dir / "style.css").read_bytes()


def test_legacy_base_only_changes_the_stylesheet() -> None:
    """Check that base_legacy.html differs from the old base only by the stylesheet it links."""
    legacy = (TEMPLATES_DIR / "base_legacy.html").read_text(encoding="utf-8")

    assert "css/legacy.css" in legacy
    assert "css/style.css" not in legacy
    assert "app.css" not in legacy


def test_redesigned_pages_load_the_new_stylesheets(app: Flask, client_admin: FlaskClient) -> None:
    """Check that a page that was not redesigned still gets the framework and the compatibility wrapper.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get(_url(app, "diets.list_diets")).get_data(as_text=True)

    assert "bootstrap@5.3.3" in html
    assert "css/app.css" in html
    assert "select2-bootstrap-5-theme@1.3.0" in html
    assert 'class="app-content compat"' in html


def test_select2_defaults_are_set_before_the_page_content(client_admin: FlaskClient, app: Flask) -> None:
    """Check the order of the head scripts: jQuery, select2, then its global defaults, then the page head block.

    :param client_admin: Test client logged in as admin.
    :param app: Flask application.
    """
    html = client_admin.get(_url(app, "diets.list_diets")).get_data(as_text=True)

    jquery = html.index("jquery-3.6.0.min.js")
    select2 = html.index("select2@4.1.0-rc.0/dist/js/select2.min.js")
    defaults = html.index('defaults.set("theme", "bootstrap-5")')
    content = html.index('class="app-content compat"')
    assert jquery < select2 < defaults < content


def test_create_user_post_renders_the_home_without_dashboard_variables(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the user creation still answers 200 by rendering the home page without its dashboard variables.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    email = "created.user@test.local"
    try:
        response = client_admin.post(
            "/admin/create_user",
            data={"name": "Created User", "email": email, "password": TEST_PASSWORD, "role": "secretary"},
        )
        html = response.get_data(as_text=True)
    finally:
        with app.app_context():
            created = User.query.filter_by(email=email).first()
            if created is not None:
                db.session.delete(created)
                db.session.commit()

    soup = _soup(html)
    assert response.status_code == 200
    assert soup.select_one(".page-header-title") is not None
    assert soup.select_one("section[aria-labelledby=upcoming-title]") is None
    assert [text for text in _toast_texts(html) if email in text] == [
        f"Usuário {email} cadastrado com sucesso com a função secretary."
    ]


def test_templates_do_not_consume_flashes_themselves() -> None:
    """Check that only the toast partial reads or clears the flashed messages."""
    offenders = [
        str(path.relative_to(TEMPLATES_DIR))
        for path in TEMPLATES_DIR.rglob("*.html")
        if path.name != "_flash_toasts.html"
        and path.name != "base_legacy.html"
        and any(token in path.read_text(encoding="utf-8") for token in ("get_flashed_messages", "_flashes"))
    ]

    assert offenders == []
