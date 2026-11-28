"""Tests of the professionals and users pages: structure, actions per role, empty states and the new user form."""

import re
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup
from flask import Flask, render_template, url_for
from flask.testing import FlaskClient
from flask_login import login_user
from flask_security.utils import hash_password, verify_password

from app.forms import PASSWORD_PATTERN, PASSWORD_REQUIREMENTS, USER_ROLES
from app.models import Role, Specialists, User, db
from tests.aliases import ClientFactory, SeedData
from tests.constants import EMAILS

STRONG_PASSWORD = "Forte-Senha-1!"  # pragma: allowlist secret
PASSWORD_ERROR = f"A senha deve ter {PASSWORD_REQUIREMENTS}."
REQUIRED = "Este campo é obrigatório."
PASSWORD_REQUIRED = "Informe a senha."  # pragma: allowlist secret
DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
APP_DIR = Path(__file__).resolve().parent.parent / "app"
NEW_EMAIL = "novo.usuario@test.local"
NEW_NAME = "Novo Usuario Teste"
ROLE_LABELS = {
    "admin": "Gestor",
    "secretary": "Secretária",  # pragma: allowlist secret
    "nutritionist": "Nutricionista",
}
FORBIDDEN = "Acesso negado! Você não tem permissão para acessar essa seção."


def _soup(html: str) -> BeautifulSoup:
    """Parse an HTML document.

    :param html: HTML text.
    :return: The parsed document.
    """
    return BeautifulSoup(html, "html.parser")


def _url(app: Flask, endpoint: str, **values: Any) -> str:
    """Build a URL path outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


def _page(client: FlaskClient, url: str) -> BeautifulSoup:
    """Open a page that must answer 200.

    :param client: Test client.
    :param url: URL path of the page.
    :return: The parsed page.
    """
    response = client.get(url)
    assert response.status_code == 200
    return _soup(response.get_data(as_text=True))


def _flashes(client: FlaskClient) -> list[tuple[str, str]]:
    """Read the messages waiting in the session of a client.

    :param client: Test client.
    :return: The (category, message) pairs, in order.
    """
    with client.session_transaction() as session:
        return [(category, message) for category, message in session.get("_flashes", [])]


def _texts(elements: Any) -> list[str]:
    """Read the text of each element with the spaces collapsed.

    :param elements: Elements of a parsed page.
    :return: The texts, in order.
    """
    return [" ".join(element.get_text().split()) for element in elements]


def _unlabelled(soup: BeautifulSoup, form_selector: str) -> list[str]:
    """List the visible controls of a form that no label points to.

    :param soup: Parsed page.
    :param form_selector: CSS selector of the form.
    :return: The names of the controls without a label.
    """
    form = soup.select_one(form_selector)
    controls = form.select("input:not([type=hidden]):not([type=radio]), select, textarea")
    return [
        str(control.get("name"))
        for control in controls
        if control.get("id") is None or form.select_one("label[for='%s']" % control["id"]) is None
    ]


def _count(model: type[db.Model], app: Flask) -> int:
    """Count the rows of a table.

    :param model: Model of the table.
    :param app: Flask application.
    :return: The number of rows.
    """
    with app.app_context():
        return model.query.count()


@pytest.fixture
def professional(app: Flask) -> Iterator[int]:
    """Create a professional with a long e-mail and remove it afterwards.

    :param app: Flask application.
    :return: Id of the professional (yielded).
    """
    with app.app_context():
        row = Specialists(
            name="Profissional Pagina", cpf="000.000.000-91", tel_number="(31) 3000-0091", email="pagina@test.local"
        )
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield row_id
    with app.app_context():
        Specialists.query.filter_by(id=row_id).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def lonely_user(app: Flask) -> Iterator[int]:
    """Create a user that never signed in and remove it afterwards.

    :param app: Flask application.
    :return: Id of the user (yielded).
    """
    with app.app_context():
        user = User(
            email="nunca.acessou@test.local",
            username="Nunca Acessou",
            active=True,
            password=hash_password(STRONG_PASSWORD),
            fs_uniquifier=uuid.uuid4().hex,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id
    with app.app_context():
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
            db.session.commit()


@pytest.fixture
def created_user(app: Flask) -> Iterator[str]:
    """Provide the e-mail of an account a test creates and delete that account afterwards.

    :param app: Flask application.
    :return: The e-mail (yielded; any account with it or with the test name is deleted afterwards).
    """
    yield NEW_EMAIL
    with app.app_context():
        for user in User.query.filter((User.email == NEW_EMAIL) | (User.username == NEW_NAME)).all():
            db.session.delete(user)
        db.session.commit()


def test_professionals_page_has_the_header_and_the_primary_action(app: Flask, client_admin: FlaskClient) -> None:
    """Check the title of the professionals page and its "Novo profissional" action.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _page(client_admin, _url(app, "specialists.list_specialists"))

    assert soup.select_one("h1.page-header-title").get_text() == "Profissionais"
    action = soup.select_one(".page-header-actions a")
    assert action["href"] == _url(app, "specialists.add_specialist") and "Novo profissional" in action.get_text()
    assert soup.select_one("title").get_text() == "Profissionais · EmagreSER"


@pytest.mark.parametrize("role", ["admin", "secretary"])
def test_professionals_table_has_contact_links_and_actions(
    app: Flask, seed: SeedData, client_for: ClientFactory, professional: int, role: str
) -> None:
    """Check the columns, the tel: and mailto: links, the edit link and the remove button of each professional.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param professional: Id of the extra professional.
    :param role: Role of the user.
    """
    soup = _page(client_for(role), _url(app, "specialists.list_specialists"))

    table = soup.select_one("table.table-stack")
    assert [th.get_text() for th in table.select("thead th")] == ["Nome", "CPF", "Telefone", "E-mail", "Ações"]
    row = next(row for row in table.select("tbody tr") if "Profissional Pagina" in row.get_text())
    assert {cell["data-label"] for cell in row.select("td")} == {"Nome", "CPF", "Telefone", "E-mail", "Ações"}
    assert row.select_one("td[data-label=CPF]").get_text() == "000.000.000-91"
    phone = row.select_one("td[data-label=Telefone] a")
    assert phone["href"] == "tel:3130000091" and phone.get_text() == "(31) 3000-0091"
    mail = row.select_one("td[data-label='E-mail'] a")
    assert mail["href"] == "mailto:pagina@test.local" and mail.get_text() == "pagina@test.local"
    edit = row.select_one("a.btn")
    assert edit["href"] == _url(app, "specialists.edit_specialist", id=professional)
    assert edit.get_text().split()[0] == "Editar"
    remove = row.select_one("button[data-bs-toggle=modal]")
    assert remove["data-bs-target"] == f"#remove-specialist-{professional}"
    assert remove.get_text().split()[0] == "Remover"
    assert soup.select_one("#specialists-title").get_text() == f"{len(table.select('tbody tr'))} profissionais"


def test_each_professional_has_a_removal_dialog_with_the_same_post(
    app: Flask, client_admin: FlaskClient, professional: int
) -> None:
    """Check the dialog: question with the name, the POST with its token and the two buttons.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param professional: Id of the extra professional.
    """
    soup = _page(client_admin, _url(app, "specialists.list_specialists"))

    modal = soup.select_one(f"#remove-specialist-{professional}")
    assert modal["aria-labelledby"] == f"remove-specialist-{professional}-title"
    assert "Tem certeza de que deseja remover Profissional Pagina?" in " ".join(modal.get_text().split())
    form = modal.select_one("form.delete-specialist-form")
    assert form["method"] == "post" and form["action"] == _url(app, "specialists.delete_specialist", id=professional)
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert _texts(form.select(".modal-footer button")) == ["Cancelar", "Confirmar remoção"]
    assert len(soup.select("form[action*='/specialists/delete/']")) == len(soup.select("tbody tr"))


def test_professionals_page_without_professionals_has_an_empty_state(app: Flask, seed: SeedData) -> None:
    """Check the empty state of a clinic with no professional, with the "Novo profissional" button.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/"):
        login_user(db.session.get(User, int(seed["user_admin"])))
        html = render_template("admin/specialists/list_specialists.html", specialists=[])

    empty = _soup(html).select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Ainda não existem profissionais cadastrados"
    assert empty.select_one("a.btn")["href"] == "/specialists-manager/specialists/add"
    assert empty.select_one("a.btn").get_text() == "Novo profissional"


def test_the_nutritionist_is_still_sent_home_from_the_management_pages(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check that the access rules of the professionals and users pages did not change for the nutritionist.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as the nutritionist.
    """
    for endpoint, values in (
        ("specialists.list_specialists", {}),
        ("admin.list_users", {}),
        ("admin.create_user", {}),
        ("admin.delete_user", {"id": int(seed["user_secretary"])}),
    ):
        response = client_nutritionist.get(_url(app, endpoint, **values))

        assert response.status_code == 302 and urlparse(response.headers["Location"]).path == "/"
        assert ("danger", FORBIDDEN) in _flashes(client_nutritionist)


def test_new_professional_page_labels_every_field_and_keeps_the_script_hooks(
    app: Flask, client_admin: FlaskClient
) -> None:
    """Check the new professional form: field names, types, input modes, labels, token and the script ids.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _page(client_admin, _url(app, "specialists.add_specialist"))

    assert soup.select_one("h1.page-header-title").get_text() == "Novo profissional"
    form = soup.select_one(".card form.add-specialist-form")
    assert form["method"] == "post" and form["action"] == _url(app, "specialists.add_specialist")
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    fields = {field["name"]: field for field in form.select("input:not([type=hidden])")}
    assert list(fields) == ["name", "cpf", "tel_number", "email"]
    assert (fields["cpf"]["type"], fields["cpf"]["inputmode"], fields["cpf"]["id"]) == ("text", "numeric", "cpf")
    assert (fields["tel_number"]["type"], fields["tel_number"]["inputmode"]) == ("tel", "tel")
    assert fields["tel_number"]["id"] == "phone"
    assert (fields["email"]["type"], fields["email"]["inputmode"], fields["email"]["id"]) == ("email", "email", "email")
    assert fields["cpf"]["maxlength"] == "14" and fields["tel_number"]["maxlength"] == "15"
    assert all(field.has_attr("required") for field in fields.values())
    assert _unlabelled(soup, "form.add-specialist-form") == []
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Cadastrar profissional"
    assert form.select_one("a.btn-outline-secondary")["href"] == _url(app, "specialists.list_specialists")
    assert soup.select_one("script[src$='js/normalize_fields.js']") is not None


def test_new_professional_page_shows_every_field_error(app: Flask, client_admin: FlaskClient) -> None:
    """Check that an empty submission shows one error under each field, marks them and stores nothing.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    before = _count(Specialists, app)

    response = client_admin.post(_url(app, "specialists.add_specialist"), data={})

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    for name in ("name", "cpf", "tel_number", "email"):
        feedback = soup.select_one(f"#{'phone' if name == 'tel_number' else name}-feedback")
        assert feedback.get_text(strip=True) == REQUIRED
        control = soup.select_one(f"input[name={name}]")
        assert "is-invalid" in control["class"] and control["aria-invalid"] == "true"
    assert _count(Specialists, app) == before


def test_edit_professional_page_is_filled_with_the_saved_data(
    app: Flask, client_admin: FlaskClient, professional: int
) -> None:
    """Check the edit page: header with the name, saved values, the way back and the script.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param professional: Id of the extra professional.
    """
    soup = _page(client_admin, _url(app, "specialists.edit_specialist", id=professional))

    assert soup.select_one("h1.page-header-title").get_text() == "Editar profissional"
    form = soup.select_one(".card form.edit-specialist-form")
    assert form["action"] == _url(app, "specialists.edit_specialist", id=professional)
    assert {field["name"]: field["value"] for field in form.select("input:not([type=hidden])")} == {
        "name": "Profissional Pagina",
        "cpf": "000.000.000-91",
        "tel_number": "(31) 3000-0091",
        "email": "pagina@test.local",
    }
    assert _unlabelled(soup, "form.edit-specialist-form") == []
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Salvar alterações"
    assert soup.select_one("script[src$='js/normalize_fields.js']") is not None


def test_edit_professional_page_keeps_what_was_typed_when_it_has_errors(
    app: Flask, client_admin: FlaskClient, professional: int
) -> None:
    """Check that a rejected edit shows the typed values with the error, and changes nothing in the database.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param professional: Id of the extra professional.
    """
    response = client_admin.post(
        _url(app, "specialists.edit_specialist", id=professional),
        data={"name": "", "cpf": "999.999.999-99", "tel_number": "(11) 98888-7777", "email": "digitado@test.local"},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert soup.select_one("#name-feedback").get_text(strip=True) == REQUIRED
    assert soup.select_one("input[name=cpf]")["value"] == "999.999.999-99"
    assert soup.select_one("input[name=email]")["value"] == "digitado@test.local"
    with app.app_context():
        assert db.session.get(Specialists, professional).cpf == "000.000.000-91"


def test_a_valid_professional_edit_still_saves_and_goes_to_the_list(
    app: Flask, client_admin: FlaskClient, professional: int
) -> None:
    """Check that the same POST saves the changes and redirects to the list.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param professional: Id of the extra professional.
    """
    response = client_admin.post(
        _url(app, "specialists.edit_specialist", id=professional),
        data={
            "name": "Profissional Editado",
            "cpf": "000.000.000-91",
            "tel_number": "(31) 3000-0091",
            "email": "pagina@test.local",
        },
    )

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == _url(app, "specialists.list_specialists")
    with app.app_context():
        assert db.session.get(Specialists, professional).name == "Profissional Editado"
    assert ("success", "Profissional editado com sucesso!") in _flashes(client_admin)


def test_users_page_has_the_header_roles_and_last_access(
    app: Flask, seed: SeedData, client_admin: FlaskClient, lonely_user: int
) -> None:
    """Check the users table: role badges, last access as dd/mm/yyyy or "Ainda não acessou", and the remove link.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param lonely_user: Id of a user that never signed in.
    """
    soup = _page(client_admin, _url(app, "admin.list_users"))

    assert soup.select_one("h1.page-header-title").get_text() == "Usuários"
    action = soup.select_one(".page-header-actions a")
    assert action["href"] == _url(app, "admin.create_user") and "Novo usuário" in action.get_text()
    table = soup.select_one("table.table-stack")
    assert [th.get_text() for th in table.select("thead th")] == ["Nome", "E-mail", "Função", "Último acesso", "Ações"]
    rows = {row.select_one("td[data-label='E-mail']").get_text(): row for row in table.select("tbody tr")}
    for role, email in EMAILS.items():
        assert _texts(rows[email].select("td[data-label=Função] .badge")) == [ROLE_LABELS[role]]
        assert DATE.fullmatch(rows[email].select_one("td[data-label='Último acesso']").get_text())
    never = rows["nunca.acessou@test.local"]
    assert never.select_one("td[data-label='Último acesso']").get_text() == "Ainda não acessou"
    assert _texts(never.select("td[data-label=Função] .text-body-secondary")) == ["Sem função"]
    remove = never.select_one("a.btn")
    assert (
        remove["href"] == _url(app, "admin.delete_user", id=lonely_user) and remove.get_text().split()[0] == "Remover"
    )
    assert soup.select_one("#users-title").get_text() == f"{len(rows)} usuários"


def test_the_last_access_is_the_clinic_date(app: Flask, client_admin: FlaskClient, lonely_user: int) -> None:
    """Check that the last access shows the São Paulo date of the stored UTC time, not the UTC date.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param lonely_user: Id of a user that never signed in.
    """
    with app.app_context():
        db.session.get(User, lonely_user).last_login_at = datetime(2041, 3, 4, 1, 30)
        db.session.commit()

    soup = _page(client_admin, _url(app, "admin.list_users"))

    row = next(row for row in soup.select("tbody tr") if "nunca.acessou@test.local" in row.get_text())
    assert row.select_one("td[data-label='Último acesso']").get_text() == "03/03/2041"


def test_users_page_without_users_has_an_empty_state(app: Flask, seed: SeedData) -> None:
    """Check the empty state of a system without users, with the "Novo usuário" button.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/"):
        login_user(db.session.get(User, int(seed["user_admin"])))
        html = render_template("list_users.html", users=[])

    empty = _soup(html).select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Ainda não existem usuários cadastrados"
    assert empty.select_one("a.btn")["href"] == "/admin/create_user"


def test_delete_user_page_is_a_confirmation_card(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the removal page: the e-mail in the question, the same POST with the token and the way back.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    user_id = int(seed["user_secretary"])
    soup = _page(client_admin, _url(app, "admin.delete_user", id=user_id))

    card = soup.select_one(".confirm-card")
    assert card.select_one("h1").get_text() == "Remover usuário"
    assert f"Tem certeza de que deseja remover {EMAILS['secretary']}?" in card.get_text()
    form = card.select_one("form.delete-user-form")
    assert form["method"] == "post" and form.get("action") is None
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert form.select_one("button[type=submit]").get_text() == "Confirmar remoção"
    assert (
        form.select_one("a")["href"] == _url(app, "admin.list_users") and form.select_one("a").get_text() == "Cancelar"
    )


def test_removing_a_user_still_deletes_it_and_goes_to_the_list(
    app: Flask, client_admin: FlaskClient, lonely_user: int
) -> None:
    """Check that the same POST removes the user, flashes the message and redirects to the list.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param lonely_user: Id of a user that never signed in.
    """
    response = client_admin.post(_url(app, "admin.delete_user", id=lonely_user))

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == _url(app, "admin.list_users")
    with app.app_context():
        assert db.session.get(User, lonely_user) is None
    assert ("success", "Usuário 'nunca.acessou@test.local' removido com sucesso!") in _flashes(client_admin)


def test_new_user_page_is_a_card_form_with_a_role_choice(app: Flask, client_admin: FlaskClient) -> None:
    """Check the new user form: labels, input types, the three roles, the password rule help and the way back.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _page(client_admin, _url(app, "admin.create_user"))

    assert soup.select_one("h1.page-header-title").get_text() == "Novo usuário"
    form = soup.select_one(".card form.create-user-form")
    assert form["method"] == "post" and form["action"] == _url(app, "admin.create_user")
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert (form.select_one("input[name=email]")["type"], form.select_one("input[name=email]")["autocomplete"]) == (
        "email",
        "off",
    )
    password = form.select_one("input[name=password]")
    assert password["type"] == "password" and password["autocomplete"] == "new-password"
    assert password.get("value") in (None, "")
    help_text = form.select_one("#password-help").get_text()
    assert help_text == f"Use {PASSWORD_REQUIREMENTS}."
    assert "número" in help_text and "símbolo" in help_text and "6 caracteres" in help_text
    assert _unlabelled(soup, "form.create-user-form") == []
    radios = form.select("fieldset input[type=radio][name=role]")
    assert [
        (radio["value"], form.select_one("label[for='%s']" % radio["id"]).get_text(strip=True)) for radio in radios
    ] == [(value, label) for value, label in USER_ROLES]
    assert not any(radio.has_attr("checked") for radio in radios)
    assert form.select_one("fieldset legend").get_text() == "Função"
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Cadastrar usuário"
    assert form.select_one("a.btn-outline-secondary")["href"] == _url(app, "admin.list_users")
    assert soup.select_one("script[src*='validate_register']") is None


def test_an_empty_new_user_form_shows_every_required_error(app: Flask, client_admin: FlaskClient) -> None:
    """Check one message per required field, next to the fields, and that nothing is stored.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    before = _count(User, app)

    response = client_admin.post(_url(app, "admin.create_user"), data={})

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#name-feedback > div")) == ["Informe o nome do usuário."]
    assert _texts(soup.select("#email-feedback > div")) == ["Informe o e-mail do usuário."]
    assert _texts(soup.select("#password-feedback > div")) == ["Informe a senha."]
    assert _texts(soup.select("#role-feedback > div")) == ["Escolha a função do usuário."]
    assert _count(User, app) == before


@pytest.mark.parametrize(
    "email",
    ["sem-arroba.test.local", "a@b", "a b@test.local", "@test.local", "um@@test.local", "a@test.", "a@.local"],
)
def test_an_invalid_email_is_refused(app: Flask, client_admin: FlaskClient, created_user: str, email: str) -> None:
    """Check the e-mail format rule of the old page, now on the server.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    :param email: E-mail with a wrong format.
    """
    before = _count(User, app)

    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": email, "password": STRONG_PASSWORD, "role": "secretary"},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#email-feedback > div")) == ["Informe um e-mail válido, como nome@exemplo.com."]
    assert _count(User, app) == before


@pytest.mark.parametrize(
    "password, message",
    [
        pytest.param("Ab1!x", PASSWORD_ERROR, id="five-characters"),
        pytest.param("a", PASSWORD_ERROR, id="one-character"),
        pytest.param("abcdef1!", PASSWORD_ERROR, id="no-upper-case"),
        pytest.param("ABCDEF1!", PASSWORD_ERROR, id="no-lower-case"),
        pytest.param("Abcdefg!", PASSWORD_ERROR, id="no-number"),
        pytest.param("Abcdefg1", PASSWORD_ERROR, id="no-symbol"),
        pytest.param("Aa1 ", PASSWORD_ERROR, id="four-characters"),
        pytest.param("", PASSWORD_REQUIRED, id="empty"),
        pytest.param("      ", PASSWORD_REQUIRED, id="blanks"),
    ],
)
def test_a_weak_password_is_refused_with_every_requirement(
    app: Flask, client_admin: FlaskClient, created_user: str, password: str, message: str
) -> None:
    """Check the password rule of the old page, with a message that lists the number too.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    :param password: Password that breaks the rule.
    :param message: Message expected under the field.
    """
    before = _count(User, app)

    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": NEW_EMAIL, "password": password, "role": "secretary"},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#password-feedback > div")) == [message]
    assert _count(User, app) == before


def test_the_password_message_lists_every_requirement() -> None:
    """Check that the message and the help text name the length, both letter cases, the number and the symbol."""
    for word in ("6 caracteres", "minúscula", "maiúscula", "número", "símbolo"):
        assert word in PASSWORD_ERROR
        assert word in PASSWORD_REQUIREMENTS


@pytest.mark.parametrize(
    "password", ["Abc123!", "abC1_x", "Zz9#zz", "Aa1é.é", "Abc123é", "Senha-Forte-2026", "Aa1 xyz"]
)
def test_a_password_that_follows_the_rule_is_accepted(password: str) -> None:
    """Check the rule itself against the pattern of the old page, as the browser evaluated it.

    :param password: Password that follows the rule.
    """
    assert PASSWORD_PATTERN.match(password) is not None


@pytest.mark.parametrize("password", ["Abc123", "abc123!", "ABC123!", "Abcdef!", "Ab1!", "\nAbc12!"])
def test_a_password_that_breaks_the_rule_does_not_match(password: str) -> None:
    """Check the rule against passwords that break one requirement.

    :param password: Password that breaks the rule.
    """
    assert PASSWORD_PATTERN.match(password) is None


def test_the_form_keeps_the_typed_name_email_and_role_but_never_the_password(
    app: Flask, client_admin: FlaskClient, created_user: str
) -> None:
    """Check that a form with errors comes back filled, except for the password.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    """
    typed = "fraca-1"
    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": "  Digitado@Test.Local ", "password": typed, "role": "nutritionist"},
    )

    html = response.get_data(as_text=True)
    soup = _soup(html)
    assert response.status_code == 200
    assert soup.select_one("input[name=name]")["value"] == NEW_NAME
    assert soup.select_one("input[name=email]")["value"] == "Digitado@Test.Local"
    checked = [radio["value"] for radio in soup.select("input[type=radio][name=role]") if radio.has_attr("checked")]
    assert checked == ["nutritionist"]
    password = soup.select_one("input[name=password]")
    assert password.get("value") in (None, "")
    assert typed not in html and f'value="{typed}"' not in html
    assert _texts(soup.select("#password-feedback > div")) == [PASSWORD_ERROR]


def test_the_password_is_not_echoed_back_when_another_field_fails(
    app: Flask, client_admin: FlaskClient, created_user: str
) -> None:
    """Check that a good password is not sent back either, when the e-mail is the field that failed.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    """
    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": "invalido", "password": STRONG_PASSWORD, "role": "secretary"},
    )

    assert STRONG_PASSWORD not in response.get_data(as_text=True)


@pytest.mark.parametrize("email", [EMAILS["admin"], EMAILS["admin"].upper(), f"  {EMAILS['admin']}  "])
def test_an_email_already_registered_is_refused_whatever_the_case_or_the_blanks(
    app: Flask, client_admin: FlaskClient, created_user: str, email: str
) -> None:
    """Check the duplicate rule: trimmed and case-insensitive.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    :param email: E-mail of an existing user, written in another way.
    """
    before = _count(User, app)

    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": email, "password": STRONG_PASSWORD, "role": "secretary"},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#email-feedback > div")) == ["Já existe um usuário cadastrado com este e-mail."]
    assert _count(User, app) == before


def test_a_name_already_in_use_is_refused_instead_of_failing(
    app: Flask, seed: SeedData, client_admin: FlaskClient, created_user: str
) -> None:
    """Check that a repeated name, which the database does not allow, is a field error and not a server error.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    """
    with app.app_context():
        taken = db.session.get(User, int(seed["user_admin"])).username

    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": taken, "email": NEW_EMAIL, "password": STRONG_PASSWORD, "role": "secretary"},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#name-feedback > div")) == ["Já existe um usuário com este nome. Use outro nome."]


@pytest.mark.parametrize("role", ["superuser", "ADMIN", "", " admin", "admin;secretary"])
def test_a_role_outside_the_three_choices_is_refused(
    app: Flask, client_admin: FlaskClient, created_user: str, role: str
) -> None:
    """Check that the role is limited to the radio choices and no Role row is created for another value.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test may create.
    :param role: Role that is not one of the choices.
    """
    users, roles = _count(User, app), _count(Role, app)

    response = client_admin.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": NEW_EMAIL, "password": STRONG_PASSWORD, "role": role},
    )

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#role-feedback > div")) != []
    assert (_count(User, app), _count(Role, app)) == (users, roles)


@pytest.mark.parametrize("staff", ["admin", "secretary"])
@pytest.mark.parametrize("role", [value for value, _ in USER_ROLES])
def test_a_valid_user_is_stored_and_the_list_shows_the_flash(
    app: Flask, client_for: ClientFactory, created_user: str, staff: str, role: str
) -> None:
    """Check the success: 302 to the users list, the flash with the role in Portuguese, and the stored user and role.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param created_user: E-mail the test creates.
    :param staff: Role of the staff member who creates the account.
    :param role: Role of the new account.
    """
    client = client_for(staff)

    response = client.post(
        _url(app, "admin.create_user"),
        data={"name": f"  {NEW_NAME} ", "email": f"  {NEW_EMAIL} ", "password": STRONG_PASSWORD, "role": role},
    )

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == _url(app, "admin.list_users")
    label = dict(USER_ROLES)[role]
    assert ("success", f"Usuário {NEW_EMAIL} cadastrado com sucesso com a função {label}.") in _flashes(client)
    with app.app_context():
        user = User.query.filter_by(email=NEW_EMAIL).one()
        assert user.username == NEW_NAME
        assert user.active is True
        assert [item.name for item in user.roles] == [role]
        assert user.password != STRONG_PASSWORD and verify_password(STRONG_PASSWORD, user.password)
        assert user.fs_uniquifier and len(user.fs_uniquifier) == 32
    followed = _page(client, response.headers["Location"])
    assert any(NEW_EMAIL in toast.get_text() for toast in followed.select("#toast-region .toast-body"))
    assert NEW_EMAIL in followed.select_one("table").get_text()


def test_the_role_row_is_created_when_it_is_missing(app: Flask, client_admin: FlaskClient, created_user: str) -> None:
    """Check that choosing a role that has no row yet creates it, as the old page did.

    The existing row is renamed for the duration of the test and put back afterwards.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param created_user: E-mail the test creates.
    """
    with app.app_context():
        existing = Role.query.filter_by(name="secretary").one()
        existing_id = existing.id
        existing.name = "secretary-guardada"
        db.session.commit()
    try:
        response = client_admin.post(
            _url(app, "admin.create_user"),
            data={"name": NEW_NAME, "email": NEW_EMAIL, "password": STRONG_PASSWORD, "role": "secretary"},
        )

        assert response.status_code == 302
        with app.app_context():
            user = User.query.filter_by(email=NEW_EMAIL).one()
            assert [item.name for item in user.roles] == ["secretary"]
            assert user.roles[0].id != existing_id
    finally:
        with app.app_context():
            for user in User.query.filter_by(email=NEW_EMAIL).all():
                db.session.delete(user)
            db.session.commit()
            for role in Role.query.filter_by(name="secretary").all():
                db.session.delete(role)
            db.session.commit()
            db.session.get(Role, existing_id).name = "secretary"
            db.session.commit()


def test_the_nutritionist_cannot_create_users(app: Flask, client_nutritionist: FlaskClient, created_user: str) -> None:
    """Check that a POST of the nutritionist is turned away before the form is read.

    :param app: Flask application.
    :param client_nutritionist: Test client logged in as the nutritionist.
    :param created_user: E-mail the test may create.
    """
    before = _count(User, app)

    response = client_nutritionist.post(
        _url(app, "admin.create_user"),
        data={"name": NEW_NAME, "email": NEW_EMAIL, "password": STRONG_PASSWORD, "role": "admin"},
    )

    assert response.status_code == 302 and urlparse(response.headers["Location"]).path == "/"
    assert _count(User, app) == before


def test_the_old_page_script_is_gone() -> None:
    """Check that the browser-side check, with its alert, no longer exists and nothing loads it."""
    assert not (APP_DIR / "static" / "js" / "validate_register.js").exists()
    assert not any(
        "validate_register" in path.read_text(encoding="utf-8") for path in (APP_DIR / "templates").rglob("*.html")
    )
