"""E2E tests (Chrome) of the diet list, the agenda, the professionals and the users pages on both viewports."""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest
from flask import Flask
from flask_security.utils import hash_password

from app.extensions import mail
from app.models import Diet, Role, Schedules, Specialists, User, db
from tests.aliases import SeedData
from tests.constants import EMAILS, NUTRITIONIST_USERNAME, TEST_PASSWORD
from tests.e2e import classic_editor_driver
from tests.e2e.test_csrf_flows import diet_orders  # noqa: F401
from tests.e2e.test_responsive_layout import _overflow, _settle, _url
from tests.test_csrf_protection import _temporary_diet

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Request

pytestmark = pytest.mark.e2e

STRONG_PASSWORD = "Forte-Senha-1!"  # pragma: allowlist secret
NEW_EMAIL = "e2e.usuario@test.local"
NEW_NAME = "Usuario E2E Teste"
REORDER = "/diets/reorder"
ORDER_SAVED = "Nova ordem salva."
SLOW_SEND_SECONDS = 0.8


@dataclass
class Senders:
    """What the mocked senders received.

    :param whatsapp: Arguments of each WhatsApp message.
    :param mails: Recipients of each e-mail.
    """

    whatsapp: list[dict[str, Any]] = field(default_factory=list)
    mails: list[list[str]] = field(default_factory=list)


@pytest.fixture
def senders(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Senders:
    """Replace the WhatsApp and e-mail senders of the live server by slow recorders: nothing leaves the machine.

    The delay keeps the page open long enough for a second tap to reach it.

    :param app: Flask application, kept so the live server is the same process the patches apply to.
    :param monkeypatch: Pytest monkeypatch fixture.
    :return: The records of what was sent.
    """
    records = Senders()

    def whatsapp(**kwargs: Any) -> str:
        """Record a WhatsApp message and answer with a fake confirmation id.

        :param kwargs: Arguments of the call.
        :return: A fake message id.
        """
        time.sleep(SLOW_SEND_SECONDS)
        records.whatsapp.append(kwargs)
        return "SM-e2e"

    def send_mail(message: Any) -> None:
        """Record an e-mail.

        :param message: The Flask-Mail message.
        """
        time.sleep(SLOW_SEND_SECONDS)
        records.mails.append(list(message.recipients))

    monkeypatch.setattr("app.views.diets.twilio_send_diet", whatsapp)
    monkeypatch.setattr(mail, "send", send_mail)
    return records


def _login(page: Page, base_url: str, role: str = "admin") -> None:
    """Log in through the real login page.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param role: Role whose fake user logs in.
    """
    classic_editor_driver.login(page, base_url, EMAILS[role], TEST_PASSWORD)


def _errors(page: Page) -> list[str]:
    """Collect the uncaught JavaScript errors and the console errors of a page.

    :param page: Playwright page.
    :return: The list that receives each message as it happens.
    """
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    return errors


def _posts(page: Page, fragment: str) -> list[Request]:
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


def _touch_drag(page: Page, start: tuple[float, float], end: tuple[float, float], steps: int = 14) -> None:
    """Drag a finger across the page with real touch events.

    :param page: Playwright page of a touch context.
    :param start: Where the finger lands, in viewport pixels.
    :param end: Where the finger is lifted, in viewport pixels.
    :param steps: Number of intermediate moves.
    """
    session = page.context.new_cdp_session(page)
    session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": start[0], "y": start[1]}]})
    for step in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * step / steps
        y = start[1] + (end[1] - start[1]) * step / steps
        session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]})
        page.wait_for_timeout(20)
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    session.detach()


def _dom_order(page: Page) -> list[int]:
    """Read the ids of the diets in the order of the list on the page.

    :param page: Playwright page.
    :return: The diet ids, top to bottom.
    """
    return [
        int(value)
        for value in page.eval_on_selector_all("#diet-list > li", "(nodes) => nodes.map((n) => n.dataset.id)")
    ]


def _stored_order(app: Flask) -> list[int]:
    """Read the ids of the diets in the order the database lists them.

    :param app: Flask application.
    :return: The diet ids.
    """
    with app.app_context():
        return [diet.id for diet in Diet.query.order_by(Diet.order.asc(), Diet.name.asc()).all()]


def _center(box: dict[str, float]) -> tuple[float, float]:
    """Find the center of a bounding box.

    :param box: Box as Playwright reports it.
    :return: The x and y of the center.
    """
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _drag_first_handle_below_the_second(page: Page, device_name: str) -> None:
    """Drag the handle of the first diet down to the middle of the second diet, with the mouse or with a finger.

    :param page: Playwright page.
    :param device_name: "desktop" for the mouse, anything else for touch.
    """
    page.evaluate("() => window.scrollTo(0, 0)")
    handle = page.locator("#diet-list > li").nth(0).locator(".diet-handle")
    target = page.locator("#diet-list > li").nth(1).bounding_box()
    start = _center(handle.bounding_box())
    end = (start[0], target["y"] + target["height"] * 0.75)
    if device_name == "desktop":
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(end[0], end[1], steps=15)
        page.mouse.up()
    else:
        _touch_drag(page, start, end)


@pytest.mark.usefixtures("diet_orders")
def test_diet_reorder_by_dragging_the_handle_persists(app: Flask, live_server: str, device: tuple[str, Page]) -> None:
    """Drag the handle of the first diet below the second one, with the mouse and with a finger: it is stored.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    device_name, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list .diet-handle")
    before = _dom_order(page)

    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(REORDER)) as sent:
        _drag_first_handle_below_the_second(page, device_name)

    assert sent.value.status == 200
    assert sent.value.request.post_data_json["order"][0] == {"id": str(before[1]), "position": 1}
    assert _dom_order(page)[:2] == [before[1], before[0]]
    assert page.locator("#diet-order-status").inner_text() == ORDER_SAVED
    assert _stored_order(app)[:2] == [before[1], before[0]]
    page.reload()
    _settle(page)
    assert _dom_order(page)[:2] == [before[1], before[0]]
    assert errors == []


@pytest.mark.usefixtures("diet_orders")
def test_diet_reorder_by_keyboard_announces_the_result(app: Flask, live_server: str, page: Page) -> None:
    """Move a diet down with the arrow key on its handle: it moves, the result is announced and the order is stored.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list .diet-handle")
    before = _dom_order(page)
    page.locator(".diet-handle").first.focus()

    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(REORDER)) as sent:
        page.keyboard.press("ArrowDown")

    assert sent.value.status == 200
    assert _dom_order(page)[:2] == [before[1], before[0]]
    assert page.locator("#diet-order-status").inner_text() == ORDER_SAVED
    assert page.evaluate("() => document.activeElement.classList.contains('diet-handle')")
    assert _stored_order(app)[:2] == [before[1], before[0]]


@pytest.mark.usefixtures("diet_orders")
def test_a_failed_reorder_is_announced_with_the_error_text(app: Flask, live_server: str, page: Page) -> None:
    """Make the server refuse the order and check the message that tells the user what to do.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list .diet-handle")
    page.route("**" + REORDER, lambda route: route.fulfill(status=500, content_type="application/json", body="{}"))
    page.locator(".diet-handle").first.focus()

    page.keyboard.press("ArrowDown")

    status = page.locator("#diet-order-status")
    page.wait_for_function("() => document.getElementById('diet-order-status').textContent !== ''")
    assert status.inner_text() == "Não foi possível salvar a nova ordem. Atualize a página e tente novamente."
    assert status.get_attribute("aria-live") == "polite"


@pytest.mark.usefixtures("diet_orders")
def test_a_swipe_outside_the_handle_scrolls_the_page_without_reordering(
    app: Flask, live_server: str, mobile_page: Page
) -> None:
    """Swipe on the body of a card with a finger: the page scrolls and no order is posted or changed.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    """
    page = mobile_page
    with contextlib.ExitStack() as stack:
        for number in range(6):
            stack.enter_context(_temporary_diet(app, f"Dieta E2E Rolagem {number}", None, order=200 + number))
        _login(page, live_server)
        page.goto(live_server + _url(app, "diets.list_diets"))
        page.wait_for_selector("#diet-list .diet-handle")
        posts = _posts(page, REORDER)
        before, stored = _dom_order(page), _stored_order(app)
        assert page.evaluate("() => document.documentElement.scrollHeight > window.innerHeight * 1.5")
        assert page.evaluate("() => window.scrollY") == 0
        card = page.locator("#diet-list > li").nth(1).bounding_box()
        body = page.locator("#diet-list > li").nth(1).locator(".diet-name").bounding_box()

        _touch_drag(
            page, (card["x"] + card["width"] / 2, body["y"] + 40), (card["x"] + card["width"] / 2, body["y"] - 160)
        )
        page.wait_for_timeout(600)

        assert page.evaluate("() => window.scrollY") > 50
        assert _dom_order(page) == before
        assert _stored_order(app) == stored
        assert posts == []
        assert page.locator("#diet-order-status").inner_text() == ""


def test_the_handle_is_a_large_touch_target_and_the_only_one_that_stops_scrolling(
    app: Flask, live_server: str, mobile_page: Page
) -> None:
    """Check the size of the handle and that only the handle disables the touch scrolling.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    """
    page = mobile_page
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list .diet-handle")

    sizes = page.eval_on_selector_all(".diet-handle", "(n) => n.map((e) => [e.offsetWidth, e.offsetHeight])")
    assert sizes and all(width >= 44 and height >= 44 for width, height in sizes)
    actions = page.evaluate(
        """() => {
            const touch = (selector) => getComputedStyle(document.querySelector(selector)).touchAction;
            return {
                handle: touch('.diet-handle'), card: touch('#diet-list > li'), list: touch('#diet-list'),
                name: touch('.diet-name'), body: touch('body'),
            };
        }"""
    )
    assert actions["handle"] == "none"
    assert {actions["card"], actions["list"], actions["name"], actions["body"]} == {"auto"}


def test_a_search_hides_the_handles_and_the_hint_explains_why(
    app: Flask, live_server: str, device: tuple[str, Page]
) -> None:
    """Search from the page: the handles disappear, the hint shows, and clearing the search brings them back.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    page.wait_for_selector("#diet-list .diet-handle")
    handles = page.locator(".diet-handle").count()
    assert handles >= 3

    page.fill("#diet-search", "Editada")
    page.get_by_role("button", name="Buscar").click()
    page.wait_for_url("**query=Editada")

    expect(page.locator(".diet-handle")).to_have_count(0)
    expect(page.get_by_text("Limpe a busca para reordenar as dietas")).to_be_visible()
    expect(page.locator("#diet-list > li")).to_have_count(1)
    page.get_by_role("link", name="Limpar busca").click()
    expect(page.locator(".diet-handle")).to_have_count(handles)
    expect(page.get_by_text("Limpe a busca para reordenar as dietas")).to_have_count(0)


def test_a_search_without_results_offers_to_clear_it(app: Flask, live_server: str, device: tuple[str, Page]) -> None:
    """Search for a diet that does not exist: the empty state names the search and leads back to the list.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets", query="zzz sem resultado"))

    expect(page.get_by_role("heading", name="Nenhuma dieta encontrada")).to_be_visible()
    expect(page.locator(".empty-state-text")).to_contain_text("“zzz sem resultado”")
    page.locator(".empty-state").get_by_role("link", name="Limpar busca").click()
    expect(page.locator("#diet-list")).to_be_visible()


def test_send_is_disabled_without_an_edited_pdf(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]
) -> None:
    """Check that a diet that was never edited cannot be sent and says why, while an edited one can.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    plain = page.locator(f"#diet-list > li[data-id='{seed['diet_a4']}']")
    edited = page.locator(f"#diet-list > li[data-id='{seed['diet_edited']}']")

    expect(plain.get_by_role("button", name="Enviar")).to_be_disabled()
    expect(plain.get_by_text("Edite o PDF antes de enviar")).to_be_visible()
    expect(edited.get_by_role("button", name="Enviar")).to_be_enabled()
    expect(edited.get_by_text("PDF editado")).to_be_visible()
    expect(edited.get_by_text("Edite o PDF antes de enviar")).to_have_count(0)


def _open_send_dialog(page: Page, seed: SeedData) -> Locator:
    """Open the send dialog of the edited diet.

    :param page: Playwright page on the diet list.
    :param seed: Ids of the fake records.
    :return: The dialog.
    """
    from playwright.sync_api import expect

    page.locator(f"#diet-list > li[data-id='{seed['diet_edited']}']").get_by_role("button", name="Enviar").click()
    dialog = page.locator("#send-diet-modal")
    expect(dialog).to_be_visible()
    return dialog


def _pick_patient(page: Page, dialog: Locator, search: str, name: str) -> None:
    """Choose a patient in the searchable select of the dialog, typing in its search box.

    :param page: Playwright page.
    :param dialog: The send dialog.
    :param search: Text to type in the search box.
    :param name: Full name of the option that must be the only match.
    """
    from playwright.sync_api import expect

    dialog.locator(".select2-selection").click()
    box = dialog.locator(".select2-search__field")
    expect(box).to_be_visible()
    box.fill(search)
    options = dialog.locator(".select2-results__option")
    expect(options).to_have_count(1)
    expect(options.first).to_have_text(name)
    options.first.click()


def test_the_send_dialog_shows_the_diet_and_searches_patients_inside_the_modal(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]
) -> None:
    """Open the dialog: the diet name in the title, the review notice with its link, and a search that works inside it.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))

    dialog = _open_send_dialog(page, seed)

    expect(dialog.locator("#send-diet-title")).to_contain_text("Dieta Teste Editada")
    expect(dialog).to_contain_text("Antes de enviar, confira a última edição do PDF.")
    preview = dialog.get_by_role("link", name="Abrir última edição")
    assert preview.get_attribute("href") == _url(app, "diets.view_last_edition", id=int(seed["diet_edited"]))
    _pick_patient(page, dialog, "teste 3", "Paciente Teste 3")
    assert page.input_value("#send-diet-patient") == str(seed["patient_other"])
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], metrics
    dialog.get_by_role("button", name="Fechar").click()
    expect(dialog).to_be_hidden()
    _open_send_dialog(page, seed)
    assert page.input_value("#send-diet-patient") == ""
    assert errors == []


def test_the_send_dialog_asks_for_a_patient_before_sending(
    app: Flask, seed: SeedData, live_server: str, page: Page, senders: Senders
) -> None:
    """Press a send button without a patient: a message shows, nothing is posted and nothing is sent.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param senders: Records of the mocked senders.
    """
    from playwright.sync_api import expect

    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    posts = _posts(page, "/send_diet")
    dialog = _open_send_dialog(page, seed)

    dialog.get_by_role("button", name="Enviar por WhatsApp").click()

    expect(dialog.locator("#send-diet-error")).to_have_text("Selecione um paciente.")
    expect(dialog.get_by_role("button", name="Enviar por WhatsApp")).to_be_enabled()
    page.wait_for_timeout(300)
    assert posts == [] and senders.whatsapp == [] and senders.mails == []


def test_a_diet_is_sent_by_whatsapp_from_the_dialog(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page], senders: Senders
) -> None:
    """Choose a patient and send by WhatsApp through the mocked sender: the diet and the patient are the chosen ones.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param senders: Records of the mocked senders.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    dialog = _open_send_dialog(page, seed)
    _pick_patient(page, dialog, "teste 1", "Paciente Teste 1")

    dialog.get_by_role("button", name="Enviar por WhatsApp").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text(
        "Dieta 'Dieta Teste Editada' enviada com sucesso para o paciente 'Paciente Teste 1'", timeout=15_000
    )
    assert [(call["patient"], call["diet"]) for call in senders.whatsapp] == [
        ("Paciente Teste 1", "Dieta Teste Editada")
    ]
    assert senders.mails == []
    expect(page.locator("#diet-list")).to_be_visible()


def test_a_diet_is_sent_by_email_from_the_dialog(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page], senders: Senders
) -> None:
    """Choose a patient and send by e-mail through the mocked sender: the message goes to the patient's address.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param senders: Records of the mocked senders.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    dialog = _open_send_dialog(page, seed)
    _pick_patient(page, dialog, "teste 2", "Paciente Teste 2")

    dialog.get_by_role("button", name="Enviar por e-mail").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text(
        "Dieta 'Dieta Teste Editada' enviada com sucesso para o e-mail do paciente 'Paciente Teste 2'", timeout=15_000
    )
    assert senders.mails == [["paciente2@test.local"]] and senders.whatsapp == []


@pytest.mark.parametrize("button_name", ["Enviar por e-mail", "Enviar por WhatsApp"])
def test_a_double_tap_sends_only_once(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page], senders: Senders, button_name: str
) -> None:
    """Tap a send button twice in a row, as a finger does: one request reaches the server and the diet is sent once.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param senders: Records of the mocked senders.
    :param button_name: Name of the button that is tapped twice.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    posts = _posts(page, "/send_diet")
    dialog = _open_send_dialog(page, seed)
    _pick_patient(page, dialog, "teste 1", "Paciente Teste 1")

    dialog.get_by_role("button", name=button_name).dblclick(no_wait_after=True)

    expect(page.locator("#toast-region .toast-body")).to_contain_text("enviada com sucesso", timeout=15_000)
    assert len(posts) == 1
    assert len(senders.mails) + len(senders.whatsapp) == 1


def test_both_send_buttons_lock_on_the_first_submit(
    app: Flask, seed: SeedData, live_server: str, page: Page, senders: Senders
) -> None:
    """Click a send button twice inside the page: after the first submit both buttons are disabled.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param senders: Records of the mocked senders.
    """
    from playwright.sync_api import expect

    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.list_diets"))
    dialog = _open_send_dialog(page, seed)
    _pick_patient(page, dialog, "teste 1", "Paciente Teste 1")

    state = page.evaluate(
        """() => {
            const email = document.getElementById('send-diet-email');
            const whatsapp = document.getElementById('send-diet-whatsapp');
            email.click();
            const afterFirst = [email.disabled, whatsapp.disabled];
            email.click();
            return {afterFirst, busy: document.getElementById('send-diet-form').getAttribute('aria-busy')};
        }"""
    )

    assert state == {"afterFirst": [True, True], "busy": "true"}
    expect(page.locator("#toast-region .toast-body")).to_contain_text("enviada com sucesso", timeout=15_000)
    assert len(senders.mails) == 1 and senders.whatsapp == []


@dataclass
class VisitRow:
    """A schedule created for a test.

    :param id: Id of the schedule.
    :param date_text: The date as the agenda shows it.
    :param time_text: The time as the agenda shows it.
    """

    id: int
    date_text: str
    time_text: str


@pytest.fixture
def visit(app: Flask, seed: SeedData) -> Iterator[VisitRow]:
    """Create a pending schedule of a far day for one patient and remove it afterwards if the test did not.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The schedule (yielded).
    """
    with app.app_context():
        row = Schedules(
            patient_id=int(seed["patient_other"]),
            date_time=datetime(2041, 9, 10, 11, 20),
            specialist=NUTRITIONIST_USERNAME,
            status="pendente",
        )
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield VisitRow(row_id, "10/09/2041", "11:20")
    with app.app_context():
        Schedules.query.filter_by(id=row_id).delete(synchronize_session=False)
        db.session.commit()


def test_the_cancel_dialog_asks_first_and_then_removes_the_visit(
    app: Flask, live_server: str, device: tuple[str, Page], visit: VisitRow
) -> None:
    """Open the cancel dialog: it names the visit, "Voltar" keeps it, and confirming removes it with a message.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param visit: The schedule created for the test.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "schedules.list_schedules"))
    row = page.locator("tbody tr", has_text=visit.date_text)
    dialog = page.locator(f"#cancel-schedule-{visit.id}")

    row.get_by_role("button", name="Cancelar").click()

    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Paciente Teste 3")
    expect(dialog).to_contain_text(f"{visit.date_text} às {visit.time_text}")
    expect(dialog).to_contain_text("O agendamento será removido da agenda.")
    dialog.get_by_role("button", name="Voltar").click()
    expect(dialog).to_be_hidden()
    expect(row).to_have_count(1)
    with app.app_context():
        assert db.session.get(Schedules, visit.id) is not None

    row.get_by_role("button", name="Cancelar").click()
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Cancelar agendamento").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text("Agendamento removido com sucesso!")
    expect(page.locator("tbody tr", has_text=visit.date_text)).to_have_count(0)
    with app.app_context():
        assert db.session.get(Schedules, visit.id) is None
    assert errors == []


def test_the_agenda_filters_by_day_and_clears_the_filter(
    app: Flask, live_server: str, device: tuple[str, Page], visit: VisitRow
) -> None:
    """Pick a day in the filter: only that day shows, an empty day says so, and "Limpar filtro" brings the list back.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param visit: The schedule created for the test.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "schedules.list_schedules"))

    page.fill("#schedule-date", "2041-09-10")
    page.get_by_role("button", name="Filtrar").click()
    expect(page.locator("tbody tr")).to_have_count(1)
    expect(page.locator(".schedule-filter-summary")).to_contain_text("terça-feira, 10/09/2041")

    page.fill("#schedule-date", "2041-09-11")
    page.get_by_role("button", name="Filtrar").click()
    expect(page.get_by_role("heading", name="Nenhum agendamento em 11/09/2041").first).to_be_visible()

    page.get_by_role("link", name="Limpar filtro").click()
    expect(page.locator("#schedule-date")).to_have_value("")
    expect(page.get_by_role("link", name="Hoje")).to_be_visible()
    page.get_by_role("link", name="Amanhã").click()
    expect(page.locator("#schedule-date")).not_to_have_value("")


def test_the_booking_form_needs_a_patient_and_books_the_visit(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]
) -> None:
    """Submit without a patient (a message shows), then search a patient, fill the rest and book.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "schedules.schedule_action"))
    posts = _posts(page, "/schedule_action")

    page.get_by_role("button", name="Agendar consulta").click()

    expect(page.locator("#schedule-patient-error")).to_have_text("Selecione um paciente.")
    assert posts == []
    page.locator(".select2-selection").click()
    page.locator(".select2-search__field").fill("teste 2")
    page.locator(".select2-results__option").first.click()
    expect(page.locator("#schedule-patient-error")).to_have_text("")
    page.fill("#schedule-datetime", "2041-10-11T09:30")
    page.select_option("#schedule-specialist", NUTRITIONIST_USERNAME)
    try:
        page.get_by_role("button", name="Agendar consulta").click()

        expect(page.locator("#toast-region .toast-body")).to_contain_text("Consulta para 'Paciente Teste 2' agendada")
        with app.app_context():
            stored = Schedules.query.filter_by(date_time=datetime(2041, 10, 11, 9, 30)).one()
            assert stored.patient_id == int(seed["patient_schedule"]) and stored.specialist == NUTRITIONIST_USERNAME
        expect(page.locator("tbody tr", has_text="11/10/2041")).to_contain_text("09:30")
    finally:
        with app.app_context():
            Schedules.query.filter_by(date_time=datetime(2041, 10, 11, 9, 30)).delete(synchronize_session=False)
            db.session.commit()
    assert errors == []


@pytest.fixture
def professional(app: Flask) -> Iterator[int]:
    """Create a professional and remove it afterwards if the test did not.

    :param app: Flask application.
    :return: Id of the professional (yielded).
    """
    with app.app_context():
        row = Specialists(
            name="Profissional E2E", cpf="000.000.000-92", tel_number="(31) 3000-0092", email="e2e.prof@test.local"
        )
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield row_id
    with app.app_context():
        Specialists.query.filter_by(id=row_id).delete(synchronize_session=False)
        db.session.commit()


def test_the_professional_removal_dialog_asks_first(
    app: Flask, live_server: str, device: tuple[str, Page], professional: int
) -> None:
    """Open the removal dialog: "Cancelar" keeps the professional, confirming removes them with a message.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param professional: Id of the professional created for the test.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "specialists.list_specialists"))
    row = page.locator("tbody tr", has_text="Profissional E2E")
    dialog = page.locator(f"#remove-specialist-{professional}")

    row.get_by_role("button", name="Remover").click()

    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Tem certeza de que deseja remover Profissional E2E?")
    dialog.get_by_role("button", name="Cancelar").click()
    expect(dialog).to_be_hidden()
    expect(row).to_have_count(1)
    with app.app_context():
        assert db.session.get(Specialists, professional) is not None

    row.get_by_role("button", name="Remover").click()
    dialog.get_by_role("button", name="Confirmar remoção").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text("Profissional removido com sucesso!")
    expect(page.locator("tbody tr", has_text="Profissional E2E")).to_have_count(0)
    with app.app_context():
        assert db.session.get(Specialists, professional) is None
    assert errors == []


def test_the_professional_form_formats_the_fields_and_shows_the_server_errors(
    app: Flask, live_server: str, device: tuple[str, Page]
) -> None:
    """Type digits into the CPF and phone fields (the script formats them), then send a blank name and see the error.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "specialists.add_specialist"))
    before = _count(app, Specialists)

    page.fill("#name", "   ")
    page.fill("#cpf", "00000000055")
    page.fill("#phone", "31988887777")
    page.fill("#email", "form.erro@test.local")
    page.locator("#email").blur()
    expect(page.locator("#cpf")).to_have_value("000.000.000-55")
    expect(page.locator("#phone")).to_have_value("(31) 98888-7777")
    page.get_by_role("button", name="Cadastrar profissional").click()

    expect(page.locator("#name-feedback")).to_have_text("Este campo é obrigatório.")
    expect(page.locator("#name")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#cpf")).to_have_value("000.000.000-55")
    assert _count(app, Specialists) == before
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], metrics
    assert errors == []


def _count(app: Flask, model: type[db.Model]) -> int:
    """Count the rows of a table.

    :param app: Flask application.
    :param model: Model of the table.
    :return: The number of rows.
    """
    with app.app_context():
        return model.query.count()


@pytest.fixture
def new_user_cleanup(app: Flask) -> Iterator[None]:
    """Remove the accounts the new user tests create.

    :param app: Flask application.
    """
    yield
    with app.app_context():
        for user in User.query.filter((User.email == NEW_EMAIL) | (User.username == NEW_NAME)).all():
            db.session.delete(user)
        db.session.commit()


@pytest.mark.usefixtures("new_user_cleanup")
def test_a_user_is_created_after_the_errors_are_fixed(app: Flask, live_server: str, device: tuple[str, Page]) -> None:
    """Fill the form with a weak password and a used e-mail, read the errors, fix them and create the user.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    page.goto(live_server + _url(app, "admin.create_user"))
    before = _count(app, User)

    page.fill("#name", NEW_NAME)
    page.fill("#email", EMAILS["admin"].upper())
    page.fill("#password", "fraca1")
    page.get_by_label("Nutricionista").check()
    page.get_by_role("button", name="Cadastrar usuário").click()

    expect(page.locator("#email-feedback")).to_have_text("Já existe um usuário cadastrado com este e-mail.")
    expect(page.locator("#password-feedback")).to_contain_text("número")
    expect(page.locator("#name")).to_have_value(NEW_NAME)
    expect(page.locator("#email")).to_have_value(EMAILS["admin"].upper())
    expect(page.locator("#password")).to_have_value("")
    expect(page.get_by_label("Nutricionista")).to_be_checked()
    assert _count(app, User) == before
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], metrics

    page.fill("#email", NEW_EMAIL)
    page.fill("#password", STRONG_PASSWORD)
    page.get_by_role("button", name="Cadastrar usuário").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text(
        f"Usuário {NEW_EMAIL} cadastrado com sucesso com a função Nutricionista."
    )
    row = page.locator("tbody tr", has_text=NEW_EMAIL)
    expect(row).to_have_count(1)
    expect(row).to_contain_text("Nutricionista")
    expect(row).to_contain_text("Ainda não acessou")
    assert _count(app, User) == before + 1
    assert errors == []


@pytest.mark.usefixtures("new_user_cleanup")
def test_a_user_is_removed_through_the_confirmation_page(
    app: Flask, live_server: str, device: tuple[str, Page]
) -> None:
    """Remove a user from the list: the link leads to the confirmation card, which removes the user with a message.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    with app.app_context():
        role = Role.query.filter_by(name="secretary").one()
        user = User(
            email=NEW_EMAIL,
            username=NEW_NAME,
            active=True,
            password=hash_password(STRONG_PASSWORD),
            fs_uniquifier=uuid.uuid4().hex,
        )
        user.roles.append(role)
        db.session.add(user)
        db.session.commit()
    before = _count(app, User)
    _login(page, live_server)
    page.goto(live_server + _url(app, "admin.list_users"))

    page.locator("tbody tr", has_text=NEW_EMAIL).get_by_role("link", name="Remover").click()

    expect(page.get_by_role("heading", name="Remover usuário")).to_be_visible()
    expect(page.locator(".confirm-card")).to_contain_text(f"Tem certeza de que deseja remover {NEW_EMAIL}?")
    page.get_by_role("button", name="Confirmar remoção").click()

    expect(page.locator("#toast-region .toast-body")).to_contain_text(f"Usuário '{NEW_EMAIL}' removido com sucesso!")
    expect(page.locator("tbody tr", has_text=NEW_EMAIL)).to_have_count(0)
    assert _count(app, User) == before - 1


def test_a_diet_form_page_shows_the_other_name_field_only_for_other(
    app: Flask, live_server: str, device: tuple[str, Page]
) -> None:
    """Choose "Outro" in the new diet form: the extra name field appears, and it hides again for another diet.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server)
    page.goto(live_server + _url(app, "diets.add_diet"))
    other = page.locator("#other-name-field")

    expect(other).to_be_hidden()
    page.select_option("#diet-select", "Outro")
    expect(other).to_be_visible()
    expect(page.get_by_label("Outro (especifique)")).to_be_visible()
    page.select_option("#diet-select", "Dieta Detox")
    expect(other).to_be_hidden()
    expect(page.locator("input[type=file]")).to_have_attribute("accept", "application/pdf")


PAGES: list[tuple[str, str, dict[str, Any]]] = [
    ("diets-list", "diets.list_diets", {}),
    ("diets-search", "diets.list_diets", {"query": "Teste"}),
    ("diets-no-result", "diets.list_diets", {"query": "zzz"}),
    ("diet-add", "diets.add_diet", {}),
    ("diet-edit", "diets.edit_diet_raw", {"id": "@diet_a4"}),
    ("diet-delete", "diets.delete_diet", {"id": "@diet_a4"}),
    ("agenda", "schedules.list_schedules", {}),
    ("agenda-day", "schedules.list_schedules", {"date": "@schedule_future_date"}),
    ("agenda-empty-day", "schedules.list_schedules", {"date": "2041-01-02"}),
    ("agenda-invalid-day", "schedules.list_schedules", {"date": "abc"}),
    ("schedule-form", "schedules.schedule_action", {}),
    ("professionals", "specialists.list_specialists", {}),
    ("professional-add", "specialists.add_specialist", {}),
    ("professional-edit", "specialists.edit_specialist", {"id": "@specialist_other"}),
    ("users", "admin.list_users", {}),
    ("user-add", "admin.create_user", {}),
    ("user-delete", "admin.delete_user", {"id": "@user_secretary"}),
]


@pytest.mark.parametrize("name, endpoint, values", PAGES, ids=[name for name, _, _ in PAGES])
def test_every_redesigned_page_fits_the_screen_and_has_no_page_errors(
    app: Flask,
    seed: SeedData,
    live_server: str,
    device: tuple[str, Page],
    name: str,
    endpoint: str,
    values: dict[str, Any],
) -> None:
    """Open each redesigned page on both viewports: it answers 200, has no sideways scroll and no script errors.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param name: Name of the page, for the test id.
    :param endpoint: Endpoint of the page.
    :param values: Arguments of the page URL; strings starting with "@" reference the seed.
    """
    _, page = device
    errors = _errors(page)
    _login(page, live_server)
    resolved = {
        key: seed[value[1:]] if isinstance(value, str) and value.startswith("@") else value
        for key, value in values.items()
    }

    response = page.goto(live_server + _url(app, endpoint, **resolved))
    _settle(page)

    assert response is not None and response.status == 200
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], metrics
    page.wait_for_timeout(200)
    assert errors == []
