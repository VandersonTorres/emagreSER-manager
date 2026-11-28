"""E2E tests of the CSRF protection in Chrome: the real pages and scripts send the token, the server enforces it."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flask import Flask

from app.errors import CSRF_EXPIRED_MESSAGE
from app.models import AnthropometricEvaluation, Diet, Patients, SkinFolds, db
from tests import backend_helpers
from tests.aliases import SeedData
from tests.constants import EMAILS, TEST_PASSWORD
from tests.e2e import classic_editor_driver, editor_driver
from tests.e2e.test_patient_pages import _fill_new_patient_habits, _fill_new_patient_identity
from tests.e2e.test_responsive_layout import _settle, _url
from tests.patient_baselines import STORED_NEW_PATIENT
from tests.pdf_fixtures import SIZES, make_pdf
from tests.test_csrf_protection import ANNOTATION, _temporary_diet
from tests.test_csrf_rendering import csrf_on  # noqa: F401

if TYPE_CHECKING:
    from playwright.sync_api import Dialog, Page, Request, Route

pytestmark = pytest.mark.e2e

TOKEN_HEADER = "x-csrftoken"
PROBE_PATH = "/__csrf_probe__/call"
CROSS_ORIGINS = re.compile(r"^https?://(cross-origin\.test|127\.0\.0\.1:9)/")
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "*",
}
CALLER = "caller-token"
FORM_DATA = "(() => { const data = new FormData(); data.append('campo', 'valor'); return data; })()"
CROSS_URL = "https://cross-origin.test/probe"
OTHER_PORT_URL = "http://127.0.0.1:9/probe"


@dataclass(frozen=True)
class Probe:
    """One fetch call the token script must treat in a given way.

    :param name: Name of the case, used as the test id.
    :param call: JavaScript expression that makes the call; ``url`` and ``path`` are the probe address.
    :param header: What the request must carry in X-CSRFToken: "page" for the token of the page, "caller" for the
        value the caller set, or None for no header.
    :param body: Text the body of the request must contain, or None when the call has no body.
    :param other: Value the request must still carry in the X-Other header, or None.
    """

    name: str
    call: str
    header: str | None
    body: str | None = None
    other: str | None = None


PROBES = [
    Probe("string-post", 'fetch(url, {method: "POST", body: "payload"})', "page", "payload"),
    Probe("relative-post", 'fetch(path, {method: "POST", body: "payload"})', "page", "payload"),
    Probe("lowercase-method", 'fetch(url, {method: "post", body: "payload"})', "page", "payload"),
    Probe("put", 'fetch(url, {method: "PUT", body: "payload"})', "page", "payload"),
    Probe("patch", 'fetch(url, {method: "PATCH", body: "payload"})', "page", "payload"),
    Probe("delete", 'fetch(url, {method: "DELETE"})', "page"),
    Probe("url-object", 'fetch(new URL(url), {method: "POST", body: "payload"})', "page", "payload"),
    Probe("request-object", 'fetch(new Request(url, {method: "POST", body: "payload"}))', "page", "payload"),
    Probe(
        "request-with-headers",
        'fetch(new Request(url, {method: "POST", body: "payload", headers: {"X-Other": "kept"}}))',
        "page",
        "payload",
        "kept",
    ),
    Probe(
        "headers-instance",
        'fetch(url, {method: "POST", body: "payload", headers: new Headers({"X-Other": "kept"})})',
        "page",
        "payload",
        "kept",
    ),
    Probe(
        "headers-array",
        'fetch(url, {method: "POST", body: "payload", headers: [["X-Other", "kept"]]})',
        "page",
        "payload",
        "kept",
    ),
    Probe(
        "headers-object",
        'fetch(url, {method: "POST", body: "payload", headers: {"X-Other": "kept"}})',
        "page",
        "payload",
        "kept",
    ),
    Probe(
        "json-body",
        'fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: \'{"a": 1}\'})',
        "page",
        '{"a": 1}',
    ),
    Probe("form-data-body", f"fetch(url, {{method: 'POST', body: {FORM_DATA}}})", "page", 'name="campo"'),
    Probe("caller-header-object", f'fetch(url, {{method: "POST", headers: {{"x-csrftoken": "{CALLER}"}}}})', "caller"),
    Probe(
        "caller-header-instance",
        f'fetch(url, {{method: "POST", headers: new Headers({{"X-CSRFToken": "{CALLER}"}})}})',
        "caller",
    ),
    Probe("caller-header-array", f'fetch(url, {{method: "POST", headers: [["X-CSRFToken", "{CALLER}"]]}})', "caller"),
    Probe(
        "caller-header-in-request",
        f'fetch(new Request(url, {{method: "POST", headers: {{"X-CSRFToken": "{CALLER}"}}}}))',
        "caller",
    ),
    Probe("get-default", "fetch(url)", None),
    Probe("get-explicit", 'fetch(url, {method: "GET"})', None),
    Probe("head", 'fetch(url, {method: "HEAD"})', None),
    Probe("get-request-object", "fetch(new Request(url))", None),
    Probe("cross-origin-post", f'fetch("{CROSS_URL}", {{method: "POST", body: "payload"}})', None, "payload"),
    Probe("cross-origin-url-object", f'fetch(new URL("{CROSS_URL}"), {{method: "POST"}})', None),
    Probe("cross-origin-request", f'fetch(new Request("{CROSS_URL}", {{method: "POST", body: "payload"}}))', None),
    Probe("protocol-relative-post", 'fetch("//cross-origin.test/probe", {method: "POST", body: "payload"})', None),
    Probe("other-port-post", f'fetch("{OTHER_PORT_URL}", {{method: "POST", body: "payload"}})', None),
]


def _errors(page: Page) -> list[str]:
    """Collect the uncaught JavaScript errors and the console errors of a page.

    :param page: Playwright page.
    :return: The list that receives each message as it happens.
    """
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    return errors


def _accept_dialogs(page: Page) -> list[str]:
    """Accept every dialog of a page, keeping what they said.

    :param page: Playwright page.
    :return: The list that receives the message of each dialog.
    """
    messages: list[str] = []

    def accept(dialog: Dialog) -> None:
        """Record the message of a dialog and accept it.

        :param dialog: Playwright dialog.
        """
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept)
    return messages


def _record_posts(page: Page, fragment: str) -> list[Request]:
    """Record the POST requests of a page whose URL contains a fragment.

    :param page: Playwright page.
    :param fragment: Text the URL of the request must contain.
    :return: The list that receives each request as it is sent.
    """
    posts: list[Request] = []
    page.on(
        "request",
        lambda request: posts.append(request) if request.method == "POST" and fragment in request.url else None,
    )
    return posts


@pytest.fixture
def downloads_the_synthetic_pdf(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the server download the synthetic A4 PDF instead of reaching the network.

    :param app: Flask application, kept so the live server is the same process the patch applies to.
    :param monkeypatch: Pytest monkeypatch fixture.
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    monkeypatch.setattr("app.views.diets.requests.get", lambda url, *args, **kwargs: backend_helpers.FakeResponse(pdf))


@pytest.fixture
def editor_diet(app: Flask) -> Iterator[int]:
    """Create a diet whose original PDF the context serves as the synthetic PDF, and remove it afterwards.

    :param app: Flask application.
    :return: The id of the diet (yielded; the row and its edited file are removed at the end).
    """
    with _temporary_diet(app, "Dieta Csrf Editor E2E", "https://fixtures.test/csrf-editor-e2e.pdf") as diet_id:
        yield diet_id


def _edited_file(app: Flask, diet_id: int) -> Path:
    """Locate the edited PDF of a diet.

    :param app: Flask application.
    :param diet_id: Id of the diet.
    :return: The path of the file, which may not exist.
    """
    return Path(app.config["TEMP_UPLOAD_FOLDER"]) / f"dieta_personalizada_id_{diet_id}.pdf"


@pytest.mark.usefixtures("csrf_on", "downloads_the_synthetic_pdf")
def test_responsive_editor_saves_with_the_token(app: Flask, live_server: str, page: Page, editor_diet: int) -> None:
    """Save in the responsive editor with CSRF protection on: the result panel opens and the POST carried the token.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param editor_diet: Id of the temporary diet.
    """
    errors = _errors(page)
    dialogs = _accept_dialogs(page)
    posts = _record_posts(page, "/edit_diet/")
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    editor_driver.open_editor(page, live_server, editor_diet)
    editor_driver.open_add_dialog(page, 0.30, 0.30)
    editor_driver.add_text(page, "Texto com token", 12, "#000000")

    page.click("#pdfe-save")
    page.wait_for_selector("#pdfe-result[open] .pdfv[data-state=ready]", timeout=editor_driver.RENDER_TIMEOUT_MS)

    assert len(posts) == 1
    assert posts[0].headers[TOKEN_HEADER] == page.get_attribute('meta[name="csrf-token"]', "content")
    assert _edited_file(app, editor_diet).read_bytes().startswith(b"%PDF")
    assert page.locator("#pdfe-feedback").text_content().strip() == ""
    assert dialogs == [] and errors == []


@pytest.mark.usefixtures("csrf_on", "downloads_the_synthetic_pdf")
def test_previous_editor_saves_with_the_token(app: Flask, live_server: str, page: Page, editor_diet: int) -> None:
    """Save in the previous editor with CSRF protection on: the POST carries the token and the diet list opens.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param editor_diet: Id of the temporary diet.
    """
    dialogs = _accept_dialogs(page)
    posts = _record_posts(page, "/edit_diet/")
    classic_editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    classic_editor_driver.open_editor(page, live_server, editor_diet)
    classic_editor_driver.open_add_dialog(page, 0.30, 0.30)
    classic_editor_driver.add_text(page, "Texto antigo com token", 12, "#000000")
    token = page.get_attribute('meta[name="csrf-token"]', "content")

    page.click("#save-changes-btn")
    page.wait_for_url(re.compile(r".*/diets-manager/diets$"))

    assert len(posts) == 1
    assert posts[0].headers[TOKEN_HEADER] == token
    assert dialogs == ["PDF atualizado com sucesso!", "Deseja baixar o PDF editado agora?"]
    assert _edited_file(app, editor_diet).read_bytes().startswith(b"%PDF")
    with app.app_context():
        assert db.session.get(Diet, editor_diet).temp_diet_file == _edited_file(app, editor_diet).name


@pytest.mark.usefixtures("csrf_on", "downloads_the_synthetic_pdf")
def test_server_refuses_an_editor_save_without_the_token_even_in_a_logged_in_browser(
    app: Flask, live_server: str, page: Page, editor_diet: int
) -> None:
    """Post to the save endpoint with the cookies of the browser but without the token: refused, nothing written.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param editor_diet: Id of the temporary diet.
    """
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    url = live_server + _url(app, "diets.edit_diet", id=editor_diet)
    page.goto(url)
    token = page.get_attribute('meta[name="csrf-token"]', "content")

    refused = page.request.post(url, data={"annotations": [ANNOTATION]})
    assert refused.status == 400
    assert refused.json() == {"status": "error", "message": CSRF_EXPIRED_MESSAGE}
    assert not _edited_file(app, editor_diet).exists()

    accepted = page.request.post(url, data={"annotations": [ANNOTATION]}, headers={"X-CSRFToken": token})
    assert accepted.status == 200
    assert _edited_file(app, editor_diet).exists()


@pytest.fixture
def diet_orders(app: Flask) -> Iterator[dict[int, int | None]]:
    """Remember the position of every diet and put it back after the test.

    :param app: Flask application.
    :return: The positions by diet id (yielded; the positions are restored at the end).
    """
    with app.app_context():
        before = {diet.id: diet.order for diet in Diet.query.all()}
    yield before
    with app.app_context():
        for diet in Diet.query.all():
            diet.order = before.get(diet.id, diet.order)
        db.session.commit()


@pytest.mark.usefixtures("csrf_on")
def test_diet_reorder_by_drag_is_stored_with_the_token(
    app: Flask, live_server: str, page: Page, diet_orders: dict[int, int | None]
) -> None:
    """Drag the handle of the first diet below the second one with CSRF protection on: the new order is stored.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param diet_orders: Positions of the diets before the test.
    """
    errors = _errors(page)
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list li")
    items = page.locator("#diet-list li")
    ids = [int(value) for value in items.evaluate_all("(nodes) => nodes.map((node) => node.dataset.id)")]
    handle, target = items.nth(0).locator(".diet-handle").bounding_box(), items.nth(1).bounding_box()
    start_x, start_y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    end_y = target["y"] + target["height"] * 0.75

    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/diets/reorder")) as sent:
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x, end_y, steps=15)
        page.mouse.up()

    assert sent.value.status == 200
    assert sent.value.request.headers[TOKEN_HEADER] == page.get_attribute('meta[name="csrf-token"]', "content")
    assert sent.value.json()["status"] == "success"
    with app.app_context():
        stored = [diet.id for diet in Diet.query.order_by(Diet.order.asc(), Diet.name.asc()).all()]
    assert stored[:2] == [ids[1], ids[0]]
    assert errors == []


@pytest.mark.usefixtures("csrf_on")
def test_patient_is_added_through_the_form_with_the_token(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]
) -> None:
    """Fill the new patient form and submit it with CSRF protection on, on the desktop and on the phone.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    _, page = device
    stored = STORED_NEW_PATIENT["nao"]
    errors = _errors(page)
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    page.goto(live_server + _url(app, "patients.add_patient"))
    _settle(page)
    _fill_new_patient_identity(page, seed, stored, False)
    _fill_new_patient_habits(page, stored)
    assert page.locator("form.add-patient-form input[name=csrf_token]").count() == 1

    try:
        page.get_by_role("button", name="Cadastrar paciente").click()
        page.wait_for_url(re.compile(r".*/patients-manager/patients$"))

        with app.app_context():
            assert Patients.query.filter_by(name=stored["name"]).count() == 1
        assert page.locator("#toast-region .toast-body", has_text=CSRF_EXPIRED_MESSAGE).count() == 0
        assert errors == []
    finally:
        with app.app_context():
            Patients.query.filter_by(name=stored["name"]).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.usefixtures("csrf_on")
def test_evaluation_is_deleted_from_the_record_with_the_token(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int]
) -> None:
    """Delete an evaluation from the patient record with CSRF protection on: the row goes and the toast confirms.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    dialogs = _accept_dialogs(page)
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    page.goto(live_server + _url(app, "patients.view_patient", id=complete_patient["patient"]) + "#avaliacoes")
    _settle(page)

    page.get_by_role("button", name=re.compile("Excluir avaliação de")).click()

    expect(page.locator("#toast-region")).to_contain_text("Avaliação antropométrica removida com sucesso!")
    assert dialogs == ["Tem certeza que deseja remover esta avaliação?"]
    with app.app_context():
        assert db.session.get(AnthropometricEvaluation, complete_patient["evaluation"]) is None
        assert SkinFolds.query.filter_by(patient_id=complete_patient["patient"]).count() == 1


@pytest.mark.usefixtures("csrf_on")
def test_a_form_without_its_token_is_refused_with_a_toast_and_changes_nothing(
    app: Flask, live_server: str, device: tuple[str, Page], complete_patient: dict[str, int]
) -> None:
    """Remove the token input of a delete form before submitting it: the page shows the message and keeps the row.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    _, page = device
    _accept_dialogs(page)
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    page.goto(live_server + _url(app, "patients.view_patient", id=complete_patient["patient"]) + "#avaliacoes")
    _settle(page)
    page.evaluate("() => document.querySelectorAll('input[name=csrf_token]').forEach((input) => input.remove())")

    page.get_by_role("button", name=re.compile("Excluir avaliação de")).click()

    expect(page.locator("#toast-region")).to_contain_text(CSRF_EXPIRED_MESSAGE)
    assert re.search(rf"/patients/view/{complete_patient['patient']}", page.url)
    with app.app_context():
        assert db.session.get(AnthropometricEvaluation, complete_patient["evaluation"]) is not None


def _open_probe_page(page: Page, live_server: str, seen: list[Request]) -> None:
    """Open the login page, with the probe addresses answered by the test, and wait until it is loaded.

    The same origin probe and the cross origin probes are answered with a 200, and the cross origin ones also answer the
    CORS preflight, so the browser lets the page read the response.

    :param page: Playwright page.
    :param live_server: Base URL of the running test server.
    :param seen: List that receives each request the probes make, preflights included.
    """

    def same_origin(route: Route) -> None:
        """Answer a request to the same origin probe.

        :param route: Playwright route of the intercepted request.
        """
        seen.append(route.request)
        route.fulfill(status=200, body="ok", content_type="text/plain")

    def cross_origin(route: Route) -> None:
        """Answer a request to another origin, with permissive CORS headers.

        :param route: Playwright route of the intercepted request.
        """
        seen.append(route.request)
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS_HEADERS)
        else:
            route.fulfill(status=200, body="ok", content_type="text/plain", headers=CORS_HEADERS)

    page.route(re.compile(r".*/__csrf_probe__/.*"), same_origin)
    page.route(CROSS_ORIGINS, cross_origin)
    page.goto(f"{live_server}/login")
    _settle(page)


@pytest.mark.parametrize("probe", PROBES, ids=lambda probe: probe.name)
def test_token_script_adds_the_header_only_where_it_belongs(live_server: str, page: Page, probe: Probe) -> None:
    """Check the header rules of csrf.js: same origin and changing methods only, never over a header of the caller.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param probe: The fetch call under test.
    """
    seen: list[Request] = []
    _open_probe_page(page, live_server, seen)
    token = page.get_attribute('meta[name="csrf-token"]', "content")
    assert token

    status = page.evaluate(
        "async ([path, call]) => { const url = location.origin + path; return (await eval(call)).status; }",
        [PROBE_PATH, probe.call],
    )

    sent = [request for request in seen if request.method != "OPTIONS"]
    assert status == 200 and len(sent) == 1
    expected = {"page": token, "caller": CALLER, None: None}[probe.header]
    assert sent[0].headers.get(TOKEN_HEADER) == expected
    assert sent[0].headers.get("x-other") == probe.other
    if probe.body is not None:
        assert probe.body in (sent[0].post_data or "")
    if probe.header is None:
        assert [request.method for request in seen if request.method == "OPTIONS"] == []


def test_token_script_does_nothing_without_the_meta_tag(live_server: str, page: Page) -> None:
    """Check that a page without the meta tag, or with an empty one, sends its requests as they are.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    seen: list[Request] = []
    _open_probe_page(page, live_server, seen)
    call = "async (path) => (await fetch(location.origin + path, {method: 'POST', body: 'payload'})).status"

    page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').setAttribute('content', '')")
    assert page.evaluate(call, PROBE_PATH) == 200
    page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').remove()")
    assert page.evaluate(call, PROBE_PATH) == 200

    assert [request.headers.get(TOKEN_HEADER) for request in seen] == [None, None]
    assert [request.post_data for request in seen] == ["payload", "payload"]


def test_token_script_reads_the_token_when_the_request_is_made(live_server: str, page: Page) -> None:
    """Check that a token changed in the meta tag after the page loaded is the one that goes out.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    seen: list[Request] = []
    _open_probe_page(page, live_server, seen)
    page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').setAttribute('content', 'renewed')")

    page.evaluate("(path) => fetch(location.origin + path, {method: 'POST'})", PROBE_PATH)

    assert [request.headers.get(TOKEN_HEADER) for request in seen] == ["renewed"]


def test_token_script_wraps_fetch_only_once(live_server: str, page: Page) -> None:
    """Check that loading the script a second time leaves the wrapper in place instead of wrapping it again.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    seen: list[Request] = []
    _open_probe_page(page, live_server, seen)
    before = page.evaluate("() => { window.__wrapper = window.fetch; return true; }")
    assert before is True

    page.add_script_tag(url=f"{live_server}/static/js/csrf.js")

    assert page.evaluate("() => window.fetch === window.__wrapper") is True


def test_token_script_keeps_the_native_fetch_for_the_pdf_viewer_requests(live_server: str, page: Page) -> None:
    """Check that requests to other origins, such as the pdf.js CDN, go out without the header and unchanged.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    seen: list[Request] = []
    _open_probe_page(page, live_server, seen)

    page.evaluate(f"() => fetch('{CROSS_URL}', {{method: 'POST', body: 'payload'}})")

    assert [request.method for request in seen] == ["POST"]
    assert seen[0].headers.get(TOKEN_HEADER) is None
