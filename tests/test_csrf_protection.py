"""CSRF protection of the whole app: every route that changes state refuses a request without the token."""

import logging
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cloudinary.uploader
import pytest
from _pytest.mark.structures import ParameterSet
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from flask_mail import Message
from flask_wtf.csrf import validate_csrf
from itsdangerous import URLSafeTimedSerializer

from app.errors import CSRF_EXPIRED_MESSAGE, same_host_referrer
from app.extensions import csrf, mail
from app.models import AnthropometricEvaluation, Diet, Patients, Role, Schedules, SkinFolds, Specialists, User, db
from app.views.backup import EXPIRED_FORM_MESSAGE
from config import Config
from tests.aliases import ClientFactory, SeedData
from tests.backend_helpers import FakeResponse
from tests.constants import EMAILS, NUTRITIONIST_USERNAME, TEST_PASSWORD
from tests.form_helpers import form_entries
from tests.patient_baselines import STORED_NEW_PATIENT
from tests.patient_cases import REMOVED_FIELDS
from tests.pdf_fixtures import SIZES, make_pdf
from tests.test_csrf_rendering import csrf_on  # noqa: F401
from tests.test_smoke_pages import EXPECTED, ROLES, Bug, _resolve_params

APP_DIR = Path(__file__).resolve().parent.parent / "app"
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOCAL_HOST = "http://localhost"
NEW_PASSWORD = "Nova-Senha-123!"  # pragma: allowlist secret
USER_PASSWORD = "Csrf-Teste-9x!"  # pragma: allowlist secret
FILE_ENDPOINTS = {"diets.serve_temp_file", "diets.download_temp_diet"}
ANNOTATION = {
    "text": "Texto de teste",
    "x": 120,
    "y": 240,
    "fontSize": 12,
    "color": "#000000",
    "page": 1,
    "canvasWidth": 977,
    "canvasHeight": 1380,
}
CLOUDINARY_URL = "https://res.cloudinary.com/demo/raw/upload/v1/diets/csrf-teste.pdf"


@dataclass(frozen=True)
class PostRoute:
    """One endpoint that accepts POST, with the page or script that sends it and what to check when it is refused.

    :param endpoint: Flask endpoint name.
    :param sender: The page or script that sends the request, in words.
    :param files: Files of the app (relative to ``app/``) that hold the sender; the templates must carry the token.
    :param role: Role of the logged in user who posts, or "anonymous".
    :param params: Arguments of ``url_for``; strings starting with "@" reference the seed.
    :param kind: "form" for browser forms, "json" for scripts that post JSON.
    :param payload: Form fields or JSON body; strings starting with "@" reference the seed.
    :param models: Models whose rows must stay as they were.
    :param exempt: Why the route is exempt from the check, or None.
    """

    endpoint: str
    sender: str
    files: tuple[str, ...]
    role: str = "admin"
    params: dict[str, int | str] = field(default_factory=dict)
    kind: str = "form"
    payload: dict[str, Any] = field(default_factory=dict)
    models: tuple[type[db.Model], ...] = ()
    exempt: str | None = None


POST_ROUTES: list[PostRoute] = [
    PostRoute(
        "admin.create_user",
        "form of the new user page",
        ("templates/create_user.html",),
        payload={"name": "Novo Usuario", "email": "novo@test.local", "password": USER_PASSWORD, "role": "secretary"},
        models=(User, Role),
    ),
    PostRoute(
        "admin.delete_user",
        "confirmation form of the user removal page",
        ("templates/_macros.html", "templates/delete_user.html"),
        params={"id": "@user_secretary"},
        models=(User, Role),
    ),
    PostRoute(
        "backup.download_backup",
        "download form of the backup page",
        ("templates/admin/backup/backup.html",),
    ),
    PostRoute(
        "diets.add_diet",
        "form of the new diet page",
        ("templates/admin/diets/add_diet.html",),
        payload={"name": "Dieta Nova", "description": "Descricao"},
        models=(Diet,),
    ),
    PostRoute(
        "diets.delete_diet",
        "confirmation form of the diet removal page",
        ("templates/_macros.html", "templates/admin/diets/delete_diet.html"),
        params={"id": "@diet_edited"},
        models=(Diet,),
    ),
    PostRoute(
        "diets.edit_diet",
        "onSave of the responsive editor and savePDF of the previous editor (fetch with a JSON body)",
        ("static/js/pdf_editor.js", "static/js/pdf_editor_legacy.js"),
        params={"id": "@diet_a4"},
        kind="json",
        payload={"annotations": [ANNOTATION]},
        models=(Diet,),
    ),
    PostRoute(
        "diets.edit_diet_raw",
        "form of the diet skeleton edit page",
        ("templates/admin/diets/edit_diet_raw.html",),
        params={"id": "@diet_a4"},
        payload={"name": "Dieta Teste A4 Alterada", "description": "Outra descricao"},
        models=(Diet,),
    ),
    PostRoute(
        "diets.reorder_diets",
        "script of the diet list that posts the new order after a drag (fetch with a JSON body)",
        ("static/js/diet_list.js", "templates/admin/diets/list_diets.html"),
        kind="json",
        payload={"order": [{"id": "@diet_a4", "position": 9}, {"id": "@diet_edited", "position": 8}]},
        models=(Diet,),
    ),
    PostRoute(
        "diets.send_diet_email",
        "send dialog of the diet list (e-mail button)",
        ("templates/admin/diets/list_diets.html",),
        params={"diet_id": "@diet_edited"},
        payload={"patient_id": "@patient_nutritionist"},
    ),
    PostRoute(
        "diets.send_diet_wpp",
        "send dialog of the diet list (WhatsApp button)",
        ("templates/admin/diets/list_diets.html",),
        params={"diet_id": "@diet_edited"},
        payload={"patient_id": "@patient_nutritionist"},
    ),
    PostRoute(
        "patients.add_anthro",
        "form of the new evaluation page",
        ("templates/admin/patients/add_anthro.html",),
        params={"patient_id": "@patient_nutritionist"},
        payload={"data_avaliacao": "2031-01-02", "idade": "40", "peso": "70"},
        models=(AnthropometricEvaluation,),
    ),
    PostRoute(
        "patients.add_patient",
        "form of the new patient page",
        ("templates/admin/patients/add_patient.html",),
        payload={"name": "Paciente Recusado", "gender": "feminino", "birth_date": "1990-01-01"},
        models=(Patients,),
    ),
    PostRoute(
        "patients.add_skinfold",
        "form of the new measurement page",
        ("templates/admin/patients/add_skinfold.html",),
        params={"patient_id": "@patient_nutritionist"},
        payload={"data_medicao": "2031-01-02", "altura": "1.7", "peso": "70"},
        models=(SkinFolds,),
    ),
    PostRoute(
        "patients.delete_anthropometric_evaluation",
        "delete form of each evaluation of the patient record",
        ("templates/admin/patients/view_patient.html",),
        params={"patient_id": "@patient_nutritionist", "evaluation_id": "@anthro"},
        models=(AnthropometricEvaluation,),
    ),
    PostRoute(
        "patients.delete_patient",
        "confirmation form of the patient removal page",
        ("templates/_macros.html", "templates/admin/patients/delete_patient.html"),
        params={"id": "@patient_other"},
        models=(Patients, AnthropometricEvaluation, SkinFolds, Schedules),
    ),
    PostRoute(
        "patients.delete_skinfold",
        "delete form of each measurement of the patient record",
        ("templates/admin/patients/view_patient.html",),
        params={"patient_id": "@patient_nutritionist", "skinfold_id": "@skinfold"},
        models=(SkinFolds,),
    ),
    PostRoute(
        "patients.edit_anthro",
        "form of the evaluation edit page",
        ("templates/admin/patients/edit_anthro.html",),
        params={"patient_id": "@patient_nutritionist", "evaluation_id": "@anthro"},
        payload={"data_avaliacao": "2031-01-02", "idade": "77"},
        models=(AnthropometricEvaluation,),
    ),
    PostRoute(
        "patients.edit_patient",
        "form of the patient edit page",
        ("templates/admin/patients/edit_patient.html",),
        params={"id": "@patient_nutritionist"},
        payload={"name": "Paciente Alterado"},
        models=(Patients,),
    ),
    PostRoute(
        "patients.edit_skinfold",
        "form of the measurement edit page",
        ("templates/admin/patients/edit_skinfold.html",),
        params={"patient_id": "@patient_nutritionist", "skinfold_id": "@skinfold"},
        payload={"data_medicao": "2031-01-02", "peso": "99.5"},
        models=(SkinFolds,),
    ),
    PostRoute(
        "patients.view_custom_history",
        "nothing: the history is a GET page, but its route also lists POST",
        (),
        params={"id": "@patient_nutritionist", "pat_name": "Paciente Teste 1"},
        models=(Patients,),
    ),
    PostRoute(
        "schedules.delete_schedule",
        "cancel dialog of each appointment of the agenda",
        ("templates/admin/schedules/list_schedules.html",),
        params={"id": "@schedule_future"},
        models=(Schedules,),
    ),
    PostRoute(
        "schedules.schedule_action",
        "form of the new appointment page",
        ("templates/admin/schedules/schedule_action.html",),
        payload={"patient_id": "@patient_schedule", "date_time": "2031-01-02T10:00", "specialist": "Alguem"},
        models=(Schedules,),
    ),
    PostRoute(
        "security.change_password",
        "form of the change password page",
        ("templates/security/change_password.html",),
        payload={"password": TEST_PASSWORD, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
        models=(User,),
    ),
    PostRoute(
        "security.forgot_password",
        "form of the forgot password page",
        ("templates/security/forgot_password.html",),
        role="anonymous",
        payload={"email": EMAILS["admin"]},
        models=(User,),
    ),
    PostRoute(
        "security.login",
        "form of the login page",
        ("templates/security/login_user.html",),
        role="anonymous",
        payload={"email": EMAILS["admin"], "password": TEST_PASSWORD},
        models=(User,),
    ),
    PostRoute(
        "security.logout",
        "link of the user menu (a GET link; the POST form is not used)",
        ("templates/_topbar.html",),
        exempt="Flask-Security exempts its own logout view from CSRF protection",
    ),
    PostRoute(
        "security.reset_password",
        "form of the reset password page",
        ("templates/security/reset_password.html",),
        role="anonymous",
        params={"token": "token-de-teste"},
        payload={"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
        models=(User,),
    ),
    PostRoute(
        "security.verify",
        "form of the identity confirmation page",
        ("templates/security/verify.html",),
        payload={"password": TEST_PASSWORD},
        models=(User,),
    ),
    PostRoute(
        "specialists.add_specialist",
        "form of the new professional page",
        ("templates/admin/specialists/_specialist_form.html", "templates/admin/specialists/add_specialist.html"),
        payload={"name": "Profissional Recusado", "cpf": "000.000.000-55", "email": "recusado@test.local"},
        models=(Specialists,),
    ),
    PostRoute(
        "specialists.delete_specialist",
        "remove dialog of each professional of the list",
        ("templates/admin/specialists/list_specialists.html",),
        params={"id": "@specialist_other"},
        models=(Specialists,),
    ),
    PostRoute(
        "specialists.edit_specialist",
        "form of the professional edit page",
        ("templates/admin/specialists/_specialist_form.html", "templates/admin/specialists/edit_specialist.html"),
        params={"id": "@specialist_other"},
        payload={"name": "Profissional Alterado"},
        models=(Specialists,),
    ),
]


@dataclass
class Guards:
    """Records of everything that would leave the app or write outside the database if a request got through.

    :param uploads: Calls of ``cloudinary.uploader.upload``.
    :param destroys: Calls of ``cloudinary.uploader.destroy``.
    :param downloads: URLs the editor save downloaded the diet PDF from.
    :param whatsapp: Calls of the WhatsApp sender.
    :param backups: Calls that built a backup archive.
    :param mails: Messages Flask-Mail was asked to send.
    """

    uploads: list[Any] = field(default_factory=list)
    destroys: list[Any] = field(default_factory=list)
    downloads: list[str] = field(default_factory=list)
    whatsapp: list[dict[str, Any]] = field(default_factory=list)
    backups: list[Any] = field(default_factory=list)
    mails: list[Message] = field(default_factory=list)

    def untouched(self) -> bool:
        """Tell whether no recorded service was called.

        :return: True when nothing was uploaded, destroyed, downloaded, sent or built.
        """
        return not (self.uploads or self.destroys or self.downloads or self.whatsapp or self.backups or self.mails)


@pytest.fixture
def guards(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Iterator[Guards]:
    """Replace every service the views call with a recorder: nothing leaves the machine.

    The mail state of the session app was built before TESTING was turned on, so it does not suppress the sending by
    itself: the fixture suppresses it and makes any connection to a mail server fail the test.

    :param app: Flask application.
    :param monkeypatch: Pytest monkeypatch fixture.
    :return: The records (yielded; the patches are undone and the mail recording stops afterwards).
    """
    records = Guards()

    def fake_upload(*args: Any, **kwargs: Any) -> dict[str, str]:
        """Record an upload and answer with a fake URL.

        :param args: Positional arguments of the call.
        :param kwargs: Keyword arguments of the call.
        :return: A fake Cloudinary answer.
        """
        records.uploads.append((args, kwargs))
        return {"secure_url": CLOUDINARY_URL}

    def fake_destroy(*args: Any, **kwargs: Any) -> dict[str, str]:
        """Record a removal.

        :param args: Positional arguments of the call.
        :param kwargs: Keyword arguments of the call.
        :return: A fake Cloudinary answer.
        """
        records.destroys.append((args, kwargs))
        return {"result": "ok"}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> FakeResponse:
        """Record the download and answer with a synthetic PDF.

        :param url: Requested URL.
        :param args: Ignored positional arguments.
        :param kwargs: Ignored keyword arguments.
        :return: A fake response with the synthetic PDF.
        """
        records.downloads.append(url)
        return FakeResponse(make_pdf(*SIZES["a4_596x842"]))

    def fake_whatsapp(**kwargs: Any) -> str:
        """Record a WhatsApp message and answer with a fake confirmation id.

        :param kwargs: Arguments of the call.
        :return: A fake message id.
        """
        records.whatsapp.append(kwargs)
        return "SM-registrado"

    def fake_backup(*args: Any, **kwargs: Any) -> None:
        """Record a backup build and fail, as the download must never get here.

        :param args: Positional arguments of the call.
        :param kwargs: Keyword arguments of the call.
        :raises RuntimeError: Always.
        """
        records.backups.append((args, kwargs))
        raise RuntimeError("the backup must not be built")

    def fake_smtp(*args: Any, **kwargs: Any) -> None:
        """Refuse any attempt to open a connection to a mail server.

        :param args: Positional arguments of the call.
        :param kwargs: Keyword arguments of the call.
        :raises AssertionError: Always.
        """
        raise AssertionError("a test tried to open a connection to a mail server")

    monkeypatch.setattr(app.extensions["mail"], "suppress", True)
    monkeypatch.setattr("smtplib.SMTP", fake_smtp)
    monkeypatch.setattr("smtplib.SMTP_SSL", fake_smtp)
    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    monkeypatch.setattr(cloudinary.uploader, "destroy", fake_destroy)
    monkeypatch.setattr("app.views.diets.requests.get", fake_get)
    monkeypatch.setattr("app.views.diets.twilio_send_diet", fake_whatsapp)
    monkeypatch.setattr("app.views.backup.build_backup", fake_backup)
    with mail.record_messages() as outbox:
        records.mails = outbox
        yield records


def _resolve(value: Any, seed: SeedData) -> Any:
    """Replace the "@name" strings of a value, at any depth, by the matching seed ids.

    :param value: String, list or dict that may reference the seed.
    :param seed: Ids of the fake records.
    :return: The value with the references replaced.
    """
    if isinstance(value, str) and value.startswith("@"):
        return seed[value[1:]]
    if isinstance(value, dict):
        return {key: _resolve(item, seed) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, seed) for item in value]
    return value


def _url(app: Flask, endpoint: str, **values: Any) -> str:
    """Build a URL path outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


def _rows(app: Flask, models: tuple[type[db.Model], ...]) -> str:
    """Summarize every column of every row of some tables as one text, so two states can be compared.

    :param app: Flask application.
    :param models: Models whose tables are read.
    :return: A text that changes when any value of any row changes.
    """
    parts: list[str] = []
    with app.app_context():
        for model in models:
            columns = [column.key for column in model.__table__.columns]
            for row in db.session.query(model).order_by(model.id).all():
                parts.append(repr([getattr(row, column) for column in columns]))
    return "\n".join(parts)


def _files(app: Flask) -> dict[str, tuple[int, int]]:
    """List the edited PDFs of the temporary folder with their size and modification time.

    :param app: Flask application.
    :return: The (size, modification time) of each file by name.
    """
    folder = Path(app.config["TEMP_UPLOAD_FOLDER"])
    return {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in folder.iterdir()}


def _flashes(client: FlaskClient) -> list[tuple[str, str]]:
    """Read the messages waiting to be shown to the user of a client.

    :param client: Test client.
    :return: The (category, message) pairs flashed and not shown yet.
    """
    with client.session_transaction() as session:
        return [tuple(item) for item in session.get("_flashes", [])]


def _page(client: FlaskClient, url: str) -> str:
    """Open a page that must answer 200.

    :param client: Test client.
    :param url: URL path of the page.
    :return: The HTML of the page.
    """
    response = client.get(url)
    assert response.status_code == 200, f"GET {url}: {response.status_code}"
    return response.get_data(as_text=True)


def _meta_token(html: str) -> str:
    """Read the CSRF token of the meta tag of a page.

    :param html: HTML of the page.
    :return: The token.
    """
    meta = BeautifulSoup(html, "html.parser").select_one('meta[name="csrf-token"]')
    assert meta is not None and meta["content"]
    return str(meta["content"])


def _form(client: FlaskClient, url: str, selector: str) -> tuple[str, dict[str, str]]:
    """Read where a form of a page posts and what a browser would submit for it.

    :param client: Test client.
    :param url: URL path of the page.
    :param selector: CSS selector of the form.
    :return: The action URL of the form and its field values, which include the token the page rendered.
    """
    html = _page(client, url)
    form = BeautifulSoup(html, "html.parser").select_one(selector)
    assert form is not None, f"form {selector} not found in {url}"
    return str(form.get("action") or url), dict(form_entries(html, selector))


def test_every_post_route_is_listed_with_its_sender(app: Flask) -> None:
    """Check that the table lists every endpoint that accepts POST and no endpoint that does not.

    :param app: Flask application.
    """
    registered = {rule.endpoint for rule in app.url_map.iter_rules() if rule.methods & STATE_CHANGING_METHODS}
    listed = [route.endpoint for route in POST_ROUTES]

    assert len(listed) == len(set(listed)), "an endpoint is listed twice"
    assert registered - set(listed) == set(), "route that accepts POST and is missing from the table"
    assert set(listed) - registered == set(), "table lists a route that no longer accepts POST"


@pytest.mark.parametrize("route", POST_ROUTES, ids=lambda route: route.endpoint)
def test_each_sender_exists_and_carries_the_token(route: PostRoute) -> None:
    """Check that the files listed as sender exist and that the templates among them render the token.

    :param route: Row of the table.
    """
    assert route.sender
    sources = {name: (APP_DIR / name).read_text(encoding="utf-8") for name in route.files}
    templates = [source for name, source in sources.items() if name.endswith(".html")]
    if templates and route.exempt is None:
        assert any("csrf_token" in source or "hidden_tag" in source for source in templates), "no token in the sender"


def test_only_flask_security_exempts_a_route(app: Flask) -> None:
    """Check that the app exempts no endpoint itself: the only exemption is the logout of Flask-Security.

    :param app: Flask application.
    """
    assert csrf._exempt_views == {"flask_security.views.logout"}
    assert csrf._exempt_blueprints == set()
    assert [route.endpoint for route in POST_ROUTES if route.exempt] == ["security.logout"]


def test_the_token_never_expires_by_itself(app: Flask) -> None:
    """Check that the time limit of the token is off in the real settings and in the app.

    :param app: Flask application.
    """
    assert Config.WTF_CSRF_TIME_LIMIT is None
    assert app.config["WTF_CSRF_TIME_LIMIT"] is None


def test_the_message_is_the_one_of_the_forms() -> None:
    """Check that the sentence of the handler is the one the backup view and the form errors macro show."""
    macros = (APP_DIR / "templates" / "_macros.html").read_text(encoding="utf-8")

    assert CSRF_EXPIRED_MESSAGE == EXPIRED_FORM_MESSAGE
    assert CSRF_EXPIRED_MESSAGE in macros


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize(
    "route", [route for route in POST_ROUTES if route.exempt is None], ids=lambda route: route.endpoint
)
def test_post_without_the_token_is_refused_and_changes_nothing(
    app: Flask, seed: SeedData, client_for: ClientFactory, guards: Guards, route: PostRoute
) -> None:
    """Check that a POST without token is refused with the message, writes nothing and calls no service.

    The user has a page open, so the session already has its token; the request just does not carry it.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param guards: Records of the services the views call.
    :param route: Row of the table.
    """
    url = _url(app, route.endpoint, **_resolve_params(route.params, seed))
    payload = _resolve(route.payload, seed)
    client = client_for(route.role)
    _page(client, "/login" if route.role == "anonymous" else "/")
    rows, files = _rows(app, route.models), _files(app)

    if route.kind == "json":
        response = client.post(url, json=payload)
    else:
        response = client.post(url, data={key: str(value) for key, value in payload.items()})

    if route.kind == "json":
        assert response.status_code == 400
        assert response.get_json() == {"status": "error", "message": CSRF_EXPIRED_MESSAGE}
    else:
        assert response.status_code == 302
        assert ("error", CSRF_EXPIRED_MESSAGE) in _flashes(client)
    assert _rows(app, route.models) == rows
    assert _files(app) == files
    assert guards.untouched()


@pytest.mark.usefixtures("csrf_on")
def test_logout_keeps_working_as_a_link(client_for: ClientFactory) -> None:
    """Check that the user menu link, a GET, logs out with CSRF protection on.

    :param client_for: Factory of test clients by role.
    """
    client = client_for("admin")

    response = client.get("/logout")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/login"


def _page_cases() -> Iterator[ParameterSet]:
    """Expand the smoke table into the (row, role) pairs that answer an HTML page.

    :return: A generator of pytest params with ids "<endpoint>[<label>]-<role>".
    """
    for item in EXPECTED:
        if item["endpoint"] in FILE_ENDPOINTS:
            continue
        for role in ROLES:
            expected = item["expected"][role]
            if not isinstance(expected, Bug) and expected == 200:
                yield pytest.param(item, role, id=f"{item['endpoint']}[{item['label']}]-{role}")


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize("item, role", list(_page_cases()))
def test_every_page_renders_valid_tokens(
    app: Flask, seed: SeedData, client_for: ClientFactory, item: dict[str, Any], role: str
) -> None:
    """Check that each page has the meta token and that every form that posts carries a valid token.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param item: Row of the smoke table.
    :param role: Role that opens the page.
    """
    url = _url(app, item["endpoint"], **_resolve_params(item["params"], seed))
    client = client_for(role)

    with client:
        response = client.get(url)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        validate_csrf(_meta_token(html))
        forms = [form for form in BeautifulSoup(html, "html.parser").find_all("form") if _posts(form)]
        for form in forms:
            token_input = form.select_one("input[name=csrf_token]")
            assert token_input is not None, f"a form that posts to {form.get('action')!r} has no token"
            validate_csrf(str(token_input["value"]))


def _posts(form: Any) -> bool:
    """Tell whether a form is sent with the POST method.

    :param form: The form element.
    :return: True for method post, in any letter case.
    """
    return str(form.get("method") or "get").lower() == "post"


@pytest.mark.usefixtures("csrf_on")
def test_previous_editor_loads_the_token_script_before_its_own(
    app: Flask, seed: SeedData, client_for: ClientFactory
) -> None:
    """Check that the previous editor has a valid meta token and the token script before its own script.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    """
    url = _url(app, "diets.edit_diet", id=int(seed["diet_a4"]), legacy=1)
    client = client_for("admin")

    with client:
        html = _page(client, url)
        validate_csrf(_meta_token(html))

    assert "css/legacy.css" in html
    assert html.index("js/csrf.js") < html.index("js/pdf_editor_legacy.js")


@pytest.mark.usefixtures("csrf_on")
def test_responsive_editor_loads_the_token_script_before_its_own(
    app: Flask, seed: SeedData, client_for: ClientFactory
) -> None:
    """Check that the responsive editor loads the token script before its own script.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    """
    html = _page(client_for("admin"), _url(app, "diets.edit_diet", id=int(seed["diet_a4"])))

    assert html.index("js/csrf.js") < html.index("js/pdf_editor.js")


def test_the_token_script_is_served_and_does_not_log_nor_ask(client: FlaskClient) -> None:
    """Check that the script is served, documented, wrapped in an IIFE, and uses no console and no dialog.

    :param client: Anonymous test client.
    """
    response = client.get("/static/js/csrf.js")

    source = response.get_data(as_text=True)
    assert response.status_code == 200
    assert not re.search(r"console\.|alert\(|confirm\(|prompt\(", source)
    assert re.match(r"/\*\*(?:(?!\*/).)*\*/\n\(function \(\) \{\n", source, re.DOTALL)
    assert source.rstrip().endswith("})();")


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize("role, path", [("anonymous", "/login"), ("admin", "/")])
def test_both_layouts_carry_the_token_and_the_script(client_for: ClientFactory, role: str, path: str) -> None:
    """Check that the pages of the shell carry the meta token and the script, for guests and for users.

    :param client_for: Factory of test clients by role.
    :param role: Role that opens the page.
    :param path: URL path of the page.
    """
    html = _page(client_for(role), path)

    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one('head meta[name="csrf-token"]') is not None
    assert soup.select_one('head script[src$="/static/js/csrf.js"]') is not None


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize(
    "role, path, status",
    [("anonymous", "/nao-existe", 404), ("anonymous", "/patients-manager/patients", 403), ("admin", "/", 500)],
)
def test_error_pages_carry_a_valid_token(
    client_for: ClientFactory, monkeypatch: pytest.MonkeyPatch, role: str, path: str, status: int
) -> None:
    """Check that the 404, 403 and 500 pages, which render the head of the layout, carry a valid meta token.

    :param client_for: Factory of test clients by role.
    :param monkeypatch: Pytest monkeypatch fixture.
    :param role: Role that opens the page.
    :param path: URL path that ends in the error.
    :param status: Status of the error.
    """

    def explode(*args: object, **kwargs: object) -> None:
        """Fail like a view hitting a broken database.

        :param args: Ignored positional arguments.
        :param kwargs: Ignored keyword arguments.
        :raises RuntimeError: Always.
        """
        raise RuntimeError("database is gone")

    monkeypatch.setattr("app.views.main.upcoming_schedules", explode)
    client = client_for(role)

    with client:
        response = client.get(path)
        assert response.status_code == status
        validate_csrf(_meta_token(response.get_data(as_text=True)))


@contextmanager
def _temporary_diet(app: Flask, name: str, diet_file: str | None, order: int = 0) -> Iterator[int]:
    """Create a diet for one test and remove it, with its edited PDF, afterwards.

    :param app: Flask application.
    :param name: Name of the diet.
    :param diet_file: URL of the original PDF.
    :param order: Position in the list.
    :return: The id of the diet (yielded; the row and the edited file are removed at the end).
    """
    with app.app_context():
        diet = Diet(name=name, description="Dieta temporaria do teste", diet_file=diet_file, order=order)
        db.session.add(diet)
        db.session.commit()
        diet_id = diet.id
    try:
        yield diet_id
    finally:
        with app.app_context():
            Diet.query.filter_by(id=diet_id).delete(synchronize_session=False)
            db.session.commit()
        edited = Path(app.config["TEMP_UPLOAD_FOLDER"]) / f"dieta_personalizada_id_{diet_id}.pdf"
        edited.unlink(missing_ok=True)


@pytest.mark.usefixtures("csrf_on")
def test_new_patient_form_posts_with_its_token(app: Flask, client_admin: FlaskClient, seed: SeedData) -> None:
    """Check that the new patient form, with the token the page rendered, creates the patient.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    stored = STORED_NEW_PATIENT["nao"]
    url = _url(app, "patients.add_patient")
    action, data = _form(client_admin, url, "form.add-patient-form")
    values = {key: "" if value is None else str(value) for key, value in stored.items() if key not in REMOVED_FIELDS}
    values["phone"] = values.pop("tel_number")
    values["specialist"] = str(seed["specialist_other"])
    values["hours"] = values["hours"][:5]
    assert "csrf_token" in data

    try:
        response = client_admin.post(action, data={**data, **values})

        assert response.status_code == 302
        assert urlparse(response.headers["Location"]).path == _url(app, "patients.list_patients")
        with app.app_context():
            assert Patients.query.filter_by(name=stored["name"]).count() == 1
    finally:
        with app.app_context():
            Patients.query.filter_by(name=stored["name"]).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize(
    "selector, model, key",
    [
        ("form[action*='/evaluation/delete/']", AnthropometricEvaluation, "evaluation"),
        ("form[action*='/skinfold/delete/']", SkinFolds, "skinfold"),
    ],
)
def test_record_delete_forms_post_with_their_token(
    app: Flask,
    client_admin: FlaskClient,
    complete_patient: dict[str, int],
    selector: str,
    model: type[db.Model],
    key: str,
) -> None:
    """Check that the delete forms of the patient record remove the evaluation or the measurement.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param selector: CSS selector of the delete form.
    :param model: Model of the row the form removes.
    :param key: Key of the row in the ids of the fixture.
    """
    url = _url(app, "patients.view_patient", id=complete_patient["patient"])
    action, data = _form(client_admin, url, selector)

    response = client_admin.post(action, data=data)

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(model, complete_patient[key]) is None
        assert Patients.query.filter_by(id=complete_patient["patient"]).count() == 1


@pytest.mark.usefixtures("csrf_on")
def test_patient_removal_card_posts_with_its_token(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that the confirmation card of the patient removal, whose form comes from the macro, removes the patient.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Csrf Remocao")
    action, data = _form(client_admin, _url(app, "patients.delete_patient", id=patient_id), ".confirm-card form")

    response = client_admin.post(action, data=data)

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Patients, patient_id) is None


@pytest.mark.usefixtures("csrf_on")
def test_schedule_cancel_form_posts_with_its_token(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that the cancel form of the agenda removes the appointment.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Csrf Agenda")
    with app.app_context():
        schedule = Schedules(
            patient_id=patient_id,
            date_time=datetime.now() + timedelta(days=20),
            specialist=NUTRITIONIST_USERNAME,
            status="pendente",
        )
        db.session.add(schedule)
        db.session.commit()
        schedule_id = schedule.id
    action, data = _form(
        client_admin, _url(app, "schedules.list_schedules"), f"form[action$='/schedules/delete/{schedule_id}']"
    )

    response = client_admin.post(action, data=data)

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Schedules, schedule_id) is None


@pytest.mark.usefixtures("csrf_on")
def test_new_appointment_form_posts_with_its_token(app: Flask, client_admin: FlaskClient, seed: SeedData) -> None:
    """Check that the form of the new appointment page schedules the visit.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    action, data = _form(client_admin, _url(app, "schedules.schedule_action"), "form.add-schedule-form")
    data.update(
        {
            "patient_id": str(seed["patient_schedule"]),
            "date_time": "2041-03-04T09:00",
            "specialist": "Profissional Csrf",
        }
    )
    assert "csrf_token" in data

    try:
        response = client_admin.post(action, data=data)

        assert response.status_code == 302
        with app.app_context():
            assert Schedules.query.filter_by(specialist="Profissional Csrf").count() == 1
    finally:
        with app.app_context():
            Schedules.query.filter_by(specialist="Profissional Csrf").delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.usefixtures("csrf_on")
def test_professional_remove_form_posts_with_its_token(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the remove form of the professional list deletes the professional.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    with app.app_context():
        specialist = Specialists(
            name="Profissional Csrf", cpf="000.000.000-77", tel_number="(31) 90000-0077", email="csrf@test.local"
        )
        db.session.add(specialist)
        db.session.commit()
        specialist_id = specialist.id
    try:
        action, data = _form(
            client_admin,
            _url(app, "specialists.list_specialists"),
            f"form[action$='/specialists/delete/{specialist_id}']",
        )

        response = client_admin.post(action, data=data)

        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Specialists, specialist_id) is None
    finally:
        with app.app_context():
            Specialists.query.filter_by(id=specialist_id).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.usefixtures("csrf_on")
def test_user_is_created_and_removed_with_the_tokens_of_the_pages(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the new user form and the removal form post with their tokens and do their work.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    email = "csrf.usuario@test.local"
    action, data = _form(client_admin, _url(app, "admin.create_user"), "form.create-user-form")
    data.update({"name": "Usuario Csrf", "email": email, "password": USER_PASSWORD, "role": "secretary"})
    assert "csrf_token" in data

    try:
        created = client_admin.post(action, data=data)

        assert created.status_code == 302
        assert urlparse(created.headers["Location"]).path == _url(app, "admin.list_users")
        with app.app_context():
            user = User.query.filter_by(email=email).one()
            assert [role.name for role in user.roles] == ["secretary"]
            user_id = user.id
        action, data = _form(client_admin, _url(app, "admin.delete_user", id=user_id), "form.delete-user-form")
        removed = client_admin.post(action, data=data)

        assert removed.status_code == 302
        with app.app_context():
            assert User.query.filter_by(email=email).count() == 0
    finally:
        with app.app_context():
            User.query.filter_by(email=email).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.usefixtures("csrf_on")
def test_diet_is_removed_with_the_token_of_the_page(app: Flask, client_admin: FlaskClient, guards: Guards) -> None:
    """Check that the diet removal form deletes the diet and asks Cloudinary, mocked, to remove its file.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param guards: Records of the services the views call.
    """
    with _temporary_diet(app, "Dieta Csrf Remocao", CLOUDINARY_URL) as diet_id:
        action, data = _form(client_admin, _url(app, "diets.delete_diet", id=diet_id), "form.delete-diet-form")

        response = client_admin.post(action, data=data)

        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Diet, diet_id) is None
        assert [call[0] for call in guards.destroys] == [("diets/csrf-teste",)]


@pytest.mark.usefixtures("csrf_on")
def test_diet_is_sent_by_email_with_the_token_of_the_list(
    app: Flask, client_admin: FlaskClient, seed: SeedData, guards: Guards
) -> None:
    """Check that the send dialog of the diet list e-mails the edited PDF, with the mail suppressed.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    :param guards: Records of the services the views call.
    """
    diet_id = int(seed["diet_edited"])
    _, data = _form(client_admin, _url(app, "diets.list_diets"), "#send-diet-form")
    html = _page(client_admin, _url(app, "diets.list_diets"))
    button = BeautifulSoup(html, "html.parser").select_one(f"button.diet-send[data-email-action$='/{diet_id}']")
    data["patient_id"] = str(seed["patient_nutritionist"])

    response = client_admin.post(str(button["data-email-action"]), data=data)

    assert response.status_code == 302
    assert [message.recipients for message in guards.mails] == [["paciente1@test.local"]]
    assert any(category == "success" for category, _ in _flashes(client_admin))
    assert guards.whatsapp == []


@pytest.mark.usefixtures("csrf_on")
def test_diet_is_sent_by_whatsapp_with_the_token_of_the_list(
    app: Flask, client_admin: FlaskClient, seed: SeedData, guards: Guards
) -> None:
    """Check that the send dialog of the diet list sends the WhatsApp message through the patched sender.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    :param guards: Records of the services the views call.
    """
    diet_id = int(seed["diet_edited"])
    _, data = _form(client_admin, _url(app, "diets.list_diets"), "#send-diet-form")
    html = _page(client_admin, _url(app, "diets.list_diets"))
    button = BeautifulSoup(html, "html.parser").select_one(f"button.diet-send[data-whatsapp-action$='/{diet_id}']")
    data["patient_id"] = str(seed["patient_nutritionist"])

    response = client_admin.post(str(button["data-whatsapp-action"]), data=data)

    assert response.status_code == 302
    assert [call["patient"] for call in guards.whatsapp] == ["Paciente Teste 1"]
    assert guards.mails == []
    assert any("SM-registrado" in message for _, message in _flashes(client_admin))


@pytest.mark.usefixtures("csrf_on")
def test_reorder_needs_the_header_and_stores_the_order_with_it(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the reorder script is refused without the header and stores the order with it.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    url = _url(app, "diets.reorder_diets")
    with _temporary_diet(app, "Dieta Csrf Ordem A", None, order=101) as first:
        with _temporary_diet(app, "Dieta Csrf Ordem B", None, order=102) as second:
            token = _meta_token(_page(client_admin, _url(app, "diets.list_diets")))
            order = {"order": [{"id": first, "position": 202}, {"id": second, "position": 201}]}

            refused = client_admin.post(url, json=order)
            with app.app_context():
                assert [db.session.get(Diet, item).order for item in (first, second)] == [101, 102]
            accepted = client_admin.post(url, json=order, headers={"X-CSRFToken": token})

            assert refused.status_code == 400
            assert refused.get_json() == {"status": "error", "message": CSRF_EXPIRED_MESSAGE}
            assert accepted.status_code == 200 and accepted.get_json()["status"] == "success"
            with app.app_context():
                assert [db.session.get(Diet, item).order for item in (first, second)] == [202, 201]


@pytest.mark.usefixtures("csrf_on")
def test_editor_save_needs_the_header_and_writes_the_pdf_with_it(
    app: Flask, client_admin: FlaskClient, guards: Guards
) -> None:
    """Check that the editor save is refused without the header and writes the edited PDF with it.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param guards: Records of the services the views call.
    """
    with _temporary_diet(app, "Dieta Csrf Editor", "https://fixtures.test/csrf-editor.pdf") as diet_id:
        url = _url(app, "diets.edit_diet", id=diet_id)
        edited = Path(app.config["TEMP_UPLOAD_FOLDER"]) / f"dieta_personalizada_id_{diet_id}.pdf"
        token = _meta_token(_page(client_admin, url))

        refused = client_admin.post(url, json={"annotations": [ANNOTATION]})
        assert not edited.exists() and guards.downloads == []
        accepted = client_admin.post(url, json={"annotations": [ANNOTATION]}, headers={"X-CSRFToken": token})

        assert refused.status_code == 400
        assert refused.get_json() == {"status": "error", "message": CSRF_EXPIRED_MESSAGE}
        assert accepted.status_code == 200 and accepted.get_json()["status"] == "success"
        assert edited.read_bytes().startswith(b"%PDF")
        assert guards.downloads == ["https://fixtures.test/csrf-editor.pdf"]
        with app.app_context():
            assert db.session.get(Diet, diet_id).temp_diet_file == edited.name


@pytest.mark.usefixtures("csrf_on")
def test_the_token_is_still_valid_after_a_long_time(app: Flask, client_admin: FlaskClient) -> None:
    """Check that a token made two hours ago is accepted, as the diet editor may stay open for that long.

    The request is a remove of a professional that does not exist: it answers 404 only when the token was accepted.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    url = _url(app, "specialists.delete_specialist", id=999999)
    _page(client_admin, "/")
    with client_admin.session_transaction() as session:
        raw_token = session["csrf_token"]
    serializer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
    now = time.time()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("itsdangerous.timed.time.time", lambda: now - 7200)
        old_token = serializer.dumps(raw_token)

    response = client_admin.post(url, data={"csrf_token": old_token})

    assert response.status_code == 404


REFERRER_CASES = [
    pytest.param(f"{LOCAL_HOST}/patients-manager/patients?search=Ana", True, id="same-host-with-query"),
    pytest.param(f"{LOCAL_HOST}/", True, id="same-host-root"),
    pytest.param("https://localhost/patients-manager/patients", True, id="https-page-behind-a-proxy"),
    pytest.param("https://localhost:8443/patients-manager/patients", False, id="https-page-on-other-port"),
    pytest.param("//localhost/patients-manager/patients", False, id="protocol-relative-same-host"),
    pytest.param("//evil.example/steal", False, id="protocol-relative-other-host"),
    pytest.param("http://evil.example/steal", False, id="other-host"),
    pytest.param("http://localhost:8080/patients-manager/patients", False, id="other-port"),
    pytest.param("http://localhost.evil.example/", False, id="host-prefix"),
    pytest.param("http://localhost@evil.example/", False, id="userinfo"),
    pytest.param("http://localhost\\@evil.example/", False, id="backslash"),
    pytest.param("http:\\\\evil.example", False, id="backslash-scheme"),
    pytest.param("javascript:alert(1)", False, id="javascript"),
    pytest.param("ftp://localhost/file", False, id="ftp"),
    pytest.param("not a url", False, id="text"),
    pytest.param("/patients-manager/patients", False, id="relative"),
    pytest.param("http://localhost/pa\tth", False, id="control-character"),
    pytest.param("", False, id="empty"),
]


@pytest.mark.parametrize("referrer, accepted", REFERRER_CASES)
def test_only_a_referrer_of_this_site_is_trusted(app: Flask, referrer: str, accepted: bool) -> None:
    """Check which Referer headers the handler may redirect to.

    :param app: Flask application.
    :param referrer: Value of the Referer header.
    :param accepted: Whether the Referer belongs to this site.
    """
    with app.test_request_context(headers={"Referer": referrer}):
        assert same_host_referrer() == (referrer if accepted else None)


@pytest.mark.parametrize(
    "referrer, accepted",
    [
        ("https://localhost/patients-manager/patients", True),
        ("http://localhost/patients-manager/patients", False),
    ],
    ids=["https-page", "http-page"],
)
def test_an_https_request_only_goes_back_to_an_https_page(app: Flask, referrer: str, accepted: bool) -> None:
    """Check that a request over https goes back to an https page of the site, never to an http one.

    :param app: Flask application.
    :param referrer: Value of the Referer header.
    :param accepted: Whether the Referer may be used.
    """
    with app.test_request_context(base_url="https://localhost", headers={"Referer": referrer}):
        assert same_host_referrer() == (referrer if accepted else None)


def test_a_request_without_referrer_has_no_page_to_go_back_to(app: Flask) -> None:
    """Check that a request without the Referer header has no page to go back to.

    :param app: Flask application.
    """
    with app.test_request_context():
        assert same_host_referrer() is None


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize(
    "referrer, expected",
    [
        (f"{LOCAL_HOST}/patients-manager/patients?search=Ana", f"{LOCAL_HOST}/patients-manager/patients?search=Ana"),
        ("https://localhost/patients-manager/patients", "https://localhost/patients-manager/patients"),
        ("http://evil.example/steal", "/"),
        ("//localhost/patients-manager/patients", "/"),
        ("not a url", "/"),
        (None, "/"),
    ],
    ids=["same-host", "https-page-behind-a-proxy", "foreign-host", "protocol-relative", "malformed", "missing"],
)
def test_a_refused_form_goes_back_to_the_page_it_came_from(
    app: Flask, client_for: ClientFactory, referrer: str | None, expected: str
) -> None:
    """Check that a refused form request redirects to a same-site Referer and to the home page otherwise.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param referrer: Value of the Referer header, or None for no header.
    :param expected: Where the redirect must go.
    """
    client = client_for("admin")
    headers = {"Referer": referrer} if referrer else {}

    response = client.post(_url(app, "specialists.delete_specialist", id=999999), headers=headers)

    assert response.status_code == 302
    assert response.headers["Location"] == expected
    assert _flashes(client) == [("error", CSRF_EXPIRED_MESSAGE)]


@pytest.mark.usefixtures("csrf_on")
def test_the_message_shows_in_a_toast_of_the_page_it_goes_back_to(app: Flask, client_for: ClientFactory) -> None:
    """Check that the refused form lands on the page it came from, with the sentence in a toast.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    list_url = _url(app, "specialists.list_specialists")
    client = client_for("admin")

    response = client.post(
        _url(app, "specialists.delete_specialist", id=999999),
        headers={"Referer": f"{LOCAL_HOST}{list_url}"},
        follow_redirects=True,
    )

    toasts = BeautifulSoup(response.get_data(as_text=True), "html.parser").select("#toast-region .toast-body")
    assert response.status_code == 200
    assert response.request.path == list_url
    assert [toast.get_text().strip() for toast in toasts] == [CSRF_EXPIRED_MESSAGE]


@pytest.mark.usefixtures("csrf_on")
def test_a_json_request_gets_a_json_answer(app: Flask, client_for: ClientFactory) -> None:
    """Check that JSON requests and clients that prefer JSON get the 400 JSON answer and no redirect.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    url = _url(app, "specialists.delete_specialist", id=999999)
    client = client_for("admin")
    expected = {"status": "error", "message": CSRF_EXPIRED_MESSAGE}

    from_body = client.post(url, json={})
    from_accept = client.post(url, data={}, headers={"Accept": "application/json"})

    for response in (from_body, from_accept):
        assert response.status_code == 400
        assert response.mimetype == "application/json"
        assert response.get_json() == expected
    assert _flashes(client) == []


@pytest.mark.usefixtures("csrf_on")
def test_the_refusal_is_logged_in_one_line_without_the_token(
    app: Flask, client_for: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """Check that one warning records the method, the path and the reason, and never the token sent.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param caplog: Pytest log capture fixture.
    """
    url = _url(app, "specialists.delete_specialist", id=999999)
    secret_token = "token-secreto-do-teste"  # pragma: allowlist secret
    client = client_for("admin")
    _page(client, "/")

    with caplog.at_level(logging.WARNING):
        client.post(url, data={"csrf_token": secret_token})

    lines = [record for record in caplog.records if "CSRF" in record.getMessage()]
    assert len(lines) == 1 and lines[0].levelno == logging.WARNING
    message = lines[0].getMessage()
    assert "POST" in message and url in message and "The CSRF token is invalid." in message
    assert secret_token not in caplog.text


@pytest.mark.usefixtures("csrf_on")
def test_a_token_of_another_session_is_refused(app: Flask, client_for: ClientFactory) -> None:
    """Check that the token of one session does not work in another one.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    url = _url(app, "specialists.delete_specialist", id=999999)
    other_token = _meta_token(_page(client_for("secretary"), "/"))
    client = client_for("admin")
    _page(client, "/")

    response = client.post(url, data={"csrf_token": other_token})

    assert response.status_code == 302
    assert _flashes(client) == [("error", CSRF_EXPIRED_MESSAGE)]


@pytest.mark.usefixtures("csrf_on")
def test_a_valid_token_in_the_header_or_the_form_is_accepted(app: Flask, client_for: ClientFactory) -> None:
    """Check that the token is accepted in a form field and in the header, and the view then runs.

    The view answers 404 for a professional that does not exist, which proves the check let the request through.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    url = _url(app, "specialists.delete_specialist", id=999999)
    client = client_for("admin")
    token = _meta_token(_page(client, "/"))

    from_form = client.post(url, data={"csrf_token": token})
    from_header = client.post(url, headers={"X-CSRFToken": token})

    assert from_form.status_code == 404
    assert from_header.status_code == 404


def test_the_suite_setting_leaves_the_check_off(app: Flask, client_for: ClientFactory) -> None:
    """Check that, without the fixture, the session app keeps CSRF protection off as the rest of the suite expects.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    """
    response = client_for("admin").post(_url(app, "specialists.delete_specialist", id=999999))

    assert app.config["WTF_CSRF_ENABLED"] is False
    assert response.status_code == 404
