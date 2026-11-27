"""E2E tests in Chrome of the observation of a bioimpedance measurement: the dialog, the tab notes and the forms."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from flask import Flask

from app.models import SkinFolds
from tests.e2e.test_patient_pages import _collect_errors, _open_page
from tests.e2e.test_responsive_layout import _login, _overflow, _snap, _url
from tests.note_helpers import NOTE_BUTTON, NOTE_MODAL_ID, NOTE_TITLE, add_measurement

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

pytestmark = pytest.mark.e2e

NOTE = "Retorno em 15 dias.\nTrazer os exames de sangue."
LONG_NOTE = (
    "\n".join(f"Linha {number}: observação clínica detalhada do paciente" for number in range(1, 12)) + "\n" + "A" * 200
)
TOO_LONG_MESSAGE = "O campo não pode ter mais de 1000 caracteres."
MODAL = f"#{NOTE_MODAL_ID}"


def _record_path(app: Flask, patient_id: int, tab: str = "") -> str:
    """Build the path of the record of a patient, optionally on a tab.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :param tab: Key of the tab to open, such as ``"bioimpedancia"``.
    :return: The URL path.
    """
    return _url(app, "patients.view_patient", id=patient_id) + (f"#{tab}" if tab else "")


def _stored_notes(app: Flask, patient_id: int) -> list[str | None]:
    """List the stored observations of the measurements of a patient, by id.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :return: The observation of each measurement.
    """
    with app.app_context():
        rows = SkinFolds.query.filter_by(patient_id=patient_id).order_by(SkinFolds.id).all()
        return [row.observacoes for row in rows]


def _box(locator: Locator) -> dict[str, float]:
    """Measure an element on the page.

    :param locator: Playwright locator of a visible element.
    :return: The x, y, width and height of the element.
    """
    box = locator.bounding_box()
    assert box is not None
    return box


def _settle_dialog(page: Page) -> None:
    """Wait until the dialog of the record is fully shown, which is when it takes the focus.

    :param page: Playwright page on a record that has the dialog.
    """
    from playwright.sync_api import expect

    expect(page.locator(MODAL)).to_have_class(re.compile(r"\bshow\b"))
    expect(page.get_by_role("button", name=NOTE_BUTTON)).to_be_focused()


def test_dialog_opens_on_load_takes_the_focus_and_closes_with_the_button(
    app: Flask, live_server: str, device: tuple[str, Page], case_patients: Callable[..., int]
) -> None:
    """Check the dialog on both viewports: visible after load, focus inside, "Entendi" closes it, a reload reopens it.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    device_name, page = device
    patient_id = case_patients("Paciente Dialogo")
    add_measurement(app, patient_id, date(2026, 3, 1), "Nota antiga")
    add_measurement(app, patient_id, date(2026, 4, 2), NOTE)
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _record_path(app, patient_id))

    dialog = page.get_by_role("dialog", name=NOTE_TITLE)
    expect(dialog).to_be_visible()
    expect(page.locator(f"{MODAL} .note-modal-date")).to_have_text("Bioimpedância de 02/04/2026")
    assert page.locator(f"{MODAL} .note-modal-text").inner_text() == NOTE
    expect(page.locator(MODAL)).to_have_attribute("aria-modal", "true")
    expect(page.get_by_role("button", name=NOTE_BUTTON)).to_be_focused()
    assert page.evaluate(f"() => document.getElementById('{NOTE_MODAL_ID}').contains(document.activeElement)")
    assert "Nota antiga" not in dialog.inner_text()
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    box = _box(page.locator(f"{MODAL} .modal-dialog"))
    viewport = page.viewport_size
    assert 0 <= box["x"] and box["x"] + box["width"] <= viewport["width"]
    assert 0 <= box["y"] and box["y"] + box["height"] <= viewport["height"]
    _snap(page, device_name, "note-dialog")

    page.get_by_role("button", name=NOTE_BUTTON).click()
    expect(page.locator(MODAL)).to_be_hidden()
    expect(page.locator(".modal-backdrop")).to_have_count(0)
    expect(page.locator("#patient-name")).to_be_focused()
    assert page.evaluate("() => document.body.classList.contains('modal-open')") is False

    page.reload()
    _settle_dialog(page)
    expect(page.get_by_role("dialog", name=NOTE_TITLE)).to_be_visible()
    assert errors == []


def test_escape_closes_the_dialog_and_gives_the_focus_back_to_the_page(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that Escape closes the dialog, and the focus goes to the patient name and the page can be used again.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Escape")
    add_measurement(app, patient_id, date(2026, 4, 2), NOTE)
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _record_path(app, patient_id))
    _settle_dialog(page)

    page.keyboard.press("Escape")

    expect(page.locator(MODAL)).to_be_hidden()
    expect(page.locator("#patient-name")).to_be_focused()
    page.get_by_role("tab", name=re.compile("Bioimpedância")).click()
    expect(page.locator("#pane-bioimpedancia")).to_be_visible()
    assert errors == []


def test_keyboard_stays_inside_the_dialog_while_it_is_open(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that Tab and Shift+Tab never put the focus on a control of the page behind the dialog.

    The focus may only be on a control of the dialog or on the document, while it leaves and comes back.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Teclado")
    add_measurement(app, patient_id, date(2026, 4, 2), NOTE)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _record_path(app, patient_id))
    _settle_dialog(page)
    on_document_or_dialog = (
        f"() => document.activeElement === document.body || "
        f"document.getElementById('{NOTE_MODAL_ID}').contains(document.activeElement)"
    )

    reached = set()
    for key in ["Tab"] * 8 + ["Shift+Tab"] * 8:
        page.keyboard.press(key)
        assert page.evaluate(on_document_or_dialog), key
        reached.add(page.evaluate("() => document.activeElement.className || document.activeElement.tagName"))

    assert any("btn-close" in name for name in reached) and any("btn-primary" in name for name in reached)


def test_long_note_wraps_and_scrolls_inside_the_dialog(
    app: Flask, live_server: str, device: tuple[str, Page], case_patients: Callable[..., int]
) -> None:
    """Check a long note with an unbreakable word: no sideways scroll, line breaks kept, scroll inside the dialog.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    assert len(LONG_NOTE) <= 1000
    device_name, page = device
    patient_id = case_patients("Paciente Nota Longa")
    add_measurement(app, patient_id, date(2026, 4, 2), LONG_NOTE)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _record_path(app, patient_id))
    _settle_dialog(page)

    text = page.locator(f"{MODAL} .note-modal-text")
    assert text.inner_text() == LONG_NOTE
    assert text.evaluate("element => getComputedStyle(element).whiteSpace") == "pre-line"
    body = page.locator(f"{MODAL} .modal-body")
    assert body.evaluate("element => element.scrollWidth <= element.clientWidth")
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    dialog = _box(page.locator(f"{MODAL} .modal-dialog"))
    assert dialog["y"] >= 0 and dialog["y"] + dialog["height"] <= page.viewport_size["height"]
    footer = _box(page.get_by_role("button", name=NOTE_BUTTON))
    assert footer["y"] + footer["height"] <= page.viewport_size["height"]
    if device_name == "mobile":
        assert body.evaluate("element => element.scrollHeight > element.clientHeight")
        body.evaluate("element => { element.scrollTop = element.scrollHeight; }")
        assert body.evaluate("element => element.scrollTop") > 0
    _snap(page, device_name, "note-dialog-long")
    page.get_by_role("button", name=NOTE_BUTTON).click()
    expect(page.locator(MODAL)).to_be_hidden()


def _topmost_is_in_dialog(page: Page, selector: str) -> bool:
    """Tell whether the element drawn at the center of another element belongs to the dialog.

    A toast over the element would be the topmost one instead.

    :param page: Playwright page with the dialog open.
    :param selector: CSS selector of an element of the dialog that is in view.
    :return: True when the topmost element at the center of the selector is inside the dialog.
    """
    return page.evaluate(
        """([selector, dialogId]) => {
            const target = document.querySelector(selector).getBoundingClientRect();
            const top = document.elementFromPoint(target.x + target.width / 2, target.y + target.height / 2);
            return top !== null && document.getElementById(dialogId).contains(top);
        }""",
        [selector, NOTE_MODAL_ID],
    )


def test_success_toast_stays_behind_the_dialog_after_saving_a_long_note_on_a_phone(
    app: Flask, live_server: str, mobile_page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that the toast shown after saving never covers the title and the date of a tall dialog on a phone.

    The toast and the dialog appear together. The note is long enough for the dialog to reach the top of the 390x844
    screen, where the toast is, so the toast must be drawn below the dialog while it is open.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Aviso Celular")
    _login(mobile_page, live_server, "admin")
    _open_page(mobile_page, live_server, _url(app, "patients.add_skinfold", patient_id=patient_id))
    _fill_measurement(mobile_page, LONG_NOTE)

    mobile_page.click("form.add-skinfold-form button[type=submit]")
    mobile_page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))
    _settle_dialog(mobile_page)

    toast = mobile_page.locator("#toast-region .app-toast-success")
    expect(toast).to_be_visible()
    toast_box = _box(toast)
    header_box = _box(mobile_page.locator(f"{MODAL} .modal-header"))
    assert (
        toast_box["y"] < header_box["y"] + header_box["height"]
        and header_box["y"] < toast_box["y"] + toast_box["height"]
    )
    assert _topmost_is_in_dialog(mobile_page, f"{MODAL} .modal-title")
    assert _topmost_is_in_dialog(mobile_page, f"{MODAL} .note-modal-date")
    assert _topmost_is_in_dialog(mobile_page, f"{MODAL} .btn-close")
    _snap(mobile_page, "mobile", "note-dialog-with-toast")

    mobile_page.get_by_role("button", name=NOTE_BUTTON).click()
    expect(mobile_page.locator(MODAL)).to_be_hidden()
    assert mobile_page.evaluate("() => getComputedStyle(document.getElementById('toast-region')).zIndex") == "1090"


def test_a_note_with_a_script_is_shown_as_text(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that a note with a script tag is text in the dialog and in the tab, and that no script runs.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    hostile = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    patient_id = case_patients("Paciente Script")
    add_measurement(app, patient_id, date(2026, 4, 2), hostile)
    errors = _collect_errors(page)
    alerts: list[str] = []

    def dismiss(dialog: Any) -> None:
        """Record the message of a browser dialog and dismiss it.

        :param dialog: Playwright dialog.
        """
        alerts.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", dismiss)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _record_path(app, patient_id))
    _settle_dialog(page)
    page.wait_for_timeout(500)

    assert page.locator(f"{MODAL} .note-modal-text").inner_text() == hostile
    assert page.locator(f"{MODAL} img, {MODAL} script").count() == 0
    assert page.locator("#pane-bioimpedancia img").count() == 0
    assert page.locator(".skinfold-note-text").inner_text() == hostile
    assert alerts == [] and errors == []


def test_tab_shows_each_note_with_its_measurement_and_the_toggle_hides_them_together(
    app: Flask,
    live_server: str,
    device: tuple[str, Page],
    case_patients: Callable[..., int],
    complete_patient: dict[str, int],
) -> None:
    """Check the notes of the Bioimpedância tab: 11 columns, notes next to their row, and show more hides both.

    The measurements of days 7, 5, 3 and 1 of June have a note; with the older one of the fixture there are eight rows,
    so the toggle hides the last three measurements and the note of the day 1. The 14 columns of the evaluation table
    are checked on the same page.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param case_patients: Factory of temporary patients.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    device_name, page = device
    patient_id = complete_patient["patient"]
    for day in range(1, 8):
        add_measurement(app, patient_id, date(2026, 6, day), f"Nota do dia {day}" if day % 2 else None)
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _record_path(app, patient_id, "bioimpedancia"))
    _settle_dialog(page)
    page.get_by_role("button", name=NOTE_BUTTON).click()
    expect(page.locator(MODAL)).to_be_hidden()

    expect(page.locator("#pane-bioimpedancia")).to_be_visible()
    assert page.locator("#skinfold-table thead th").count() == 11
    assert page.locator("#anthro-table thead th").count() == 14
    measurements = page.locator("#skinfold-table tbody tr.skinfold-row")
    notes = page.locator("#skinfold-table tbody tr.skinfold-note-row")
    assert measurements.count() == 8 and notes.count() == 4
    assert [notes.nth(index).locator(".skinfold-note-text").inner_text() for index in range(4)] == [
        "Nota do dia 7",
        "Nota do dia 5",
        "Nota do dia 3",
        "Nota do dia 1",
    ]
    expect(page.locator("#skinfold-table tbody tr:visible")).to_have_count(8)
    first_row = _box(measurements.first)
    first_note = _box(notes.first)
    gap = first_note["y"] - (first_row["y"] + first_row["height"])
    assert -1 <= gap <= 2
    if device_name == "mobile":
        assert first_note["x"] == first_row["x"] and first_note["width"] == first_row["width"]
        following = _box(measurements.nth(1))
        assert following["y"] - (first_note["y"] + first_note["height"]) >= 8
        assert page.locator("#skinfold-table").evaluate("element => getComputedStyle(element).display") == "block"
    else:
        table = _box(page.locator("#skinfold-table"))
        cell = _box(notes.first.locator("td"))
        assert cell["width"] >= table["width"] - 2
        assert notes.first.locator("td").get_attribute("colspan") == "11"
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    _snap(page, device_name, "note-tab")

    toggle = page.locator("#toggleSkinfold")
    toggle.click()
    expect(page.locator("#skinfold-table tbody tr:visible")).to_have_count(12)
    expect(toggle).to_have_text("Mostrar menos medições")
    toggle.click()
    expect(page.locator("#skinfold-table tbody tr:visible")).to_have_count(8)
    hidden = page.locator("#skinfold-table tbody tr.record-row-extra")
    assert hidden.count() == 4
    assert [hidden.nth(index).is_visible() for index in range(4)] == [False] * 4
    assert errors == []


def _fill_measurement(page: Page, note: str | None) -> None:
    """Fill the new measurement form with a valid measurement and, when given, an observation.

    :param page: Playwright page on the new measurement form.
    :param note: Text typed in the observation field, or None to leave it empty.
    """
    page.fill("#data_medicao", "2026-11-20")
    page.fill("#altura", "1.7")
    page.fill("#peso", "70.5")
    page.fill("#pa", "12/8")
    if note is not None:
        page.fill("#observacoes", note)


def test_saving_and_clearing_a_note_through_the_forms(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check the whole path in the browser: a note typed in the new form opens the dialog; clearing it stops that.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Formularios")
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_skinfold", patient_id=patient_id))
    textarea = page.locator("textarea#observacoes")
    assert textarea.get_attribute("maxlength") == "1000" and textarea.get_attribute("required") is None
    expect(page.locator("#observacoes-help")).to_contain_text("ficha do paciente")
    _snap(page, "desktop", "note-add-form-empty")

    _fill_measurement(page, "Primeira linha\nSegunda linha")
    _snap(page, "desktop", "note-add-form")
    page.click("form.add-skinfold-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))

    assert _stored_notes(app, patient_id) == ["Primeira linha\nSegunda linha"]
    _settle_dialog(page)
    assert page.locator(f"{MODAL} .note-modal-text").inner_text() == "Primeira linha\nSegunda linha"
    page.get_by_role("button", name=NOTE_BUTTON).click()
    expect(page.locator(MODAL)).to_be_hidden()
    page.get_by_role("tab", name=re.compile("Bioimpedância")).click()
    page.get_by_role("link", name=re.compile("Editar medição de")).click()
    expect(page.locator("#observacoes")).to_have_value("Primeira linha\nSegunda linha")
    _snap(page, "desktop", "note-edit-form")

    page.fill("#observacoes", "  \n ")
    page.click("form.edit-skinfold-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))

    assert _stored_notes(app, patient_id) == [None]
    expect(page.locator("#patient-name")).to_be_visible()
    assert page.locator(MODAL).count() == 0
    assert errors == []


def test_a_note_over_1000_characters_is_refused_with_the_message(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that a text of 1001 characters is refused, as when the browser limit is missing, with the message.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Texto Longo")
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)
    _login(page, live_server, "admin")
    _open_page(page, live_server, url)
    page.locator("#observacoes").evaluate("element => element.removeAttribute('maxlength')")
    _fill_measurement(page, "x" * 1001)

    page.click("form.add-skinfold-form button[type=submit]")

    expect(page.locator("#observacoes-feedback")).to_have_text(TOO_LONG_MESSAGE)
    expect(page.locator("#observacoes")).to_have_class(re.compile("is-invalid"))
    assert page.url.endswith(url) and _stored_notes(app, patient_id) == []


def test_record_without_a_note_has_no_dialog_and_nothing_extra(
    app: Flask, live_server: str, device: tuple[str, Page], case_patients: Callable[..., int]
) -> None:
    """Check that a record whose latest measurement has no note opens without a dialog, with the old note in the tab.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    device_name, page = device
    patient_id = case_patients("Paciente Sem Dialogo")
    add_measurement(app, patient_id, date(2026, 3, 1), "Nota que só aparece na aba")
    add_measurement(app, patient_id, date(2026, 4, 2), None)
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _record_path(app, patient_id, "bioimpedancia"))
    page.wait_for_timeout(600)

    expect(page.locator(".modal-backdrop")).to_have_count(0)
    assert page.locator(MODAL).count() == 0
    expect(page.locator(".skinfold-note-text")).to_have_text("Nota que só aparece na aba")
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    assert errors == []


@pytest.mark.parametrize("role", ["secretary", "nutritionist"])
def test_other_roles_see_the_dialog_too(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int], role: str
) -> None:
    """Check the dialog for the secretary and for the nutritionist who owns the patient.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    :param role: Role under test.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Papeis", specialist="specialist_nutritionist")
    add_measurement(app, patient_id, date(2026, 4, 2), NOTE)
    _login(page, live_server, role)

    _open_page(page, live_server, _record_path(app, patient_id))

    expect(page.get_by_role("dialog", name=NOTE_TITLE)).to_be_visible()
    assert page.locator(f"{MODAL} .note-modal-text").inner_text() == NOTE


def test_screens_of_the_forms_on_a_phone(
    app: Flask, live_server: str, mobile_page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that the new and edit measurement forms fit a 390px phone, with the observation field in view.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    patient_id = case_patients("Paciente Formulario Celular")
    skinfold_id = add_measurement(app, patient_id, date(2026, 4, 2), NOTE)
    _login(mobile_page, live_server, "admin")

    for name, path in (
        ("note-add-form", _url(app, "patients.add_skinfold", patient_id=patient_id)),
        ("note-edit-form", _url(app, "patients.edit_skinfold", patient_id=patient_id, skinfold_id=skinfold_id)),
    ):
        _open_page(mobile_page, live_server, path)
        expect(mobile_page.locator("textarea#observacoes")).to_be_visible()
        box = _box(mobile_page.locator("textarea#observacoes"))
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        metrics = _overflow(mobile_page)
        assert metrics["scroll"] <= metrics["inner"], (name, metrics)
        _snap(mobile_page, "mobile", name)


def test_new_measurement_keeps_working_without_a_note_in_the_browser(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that the measurement is still saved, and no dialog opens, when the observation is left empty.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Sem Nota")
    errors = _collect_errors(page)
    dialogs: list[str] = []

    def dismiss(dialog: Any) -> None:
        """Record the message of a browser dialog and dismiss it.

        :param dialog: Playwright dialog.
        """
        dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", dismiss)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_skinfold", patient_id=patient_id))
    _fill_measurement(page, None)

    page.click("form.add-skinfold-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))
    page.wait_for_timeout(500)

    assert _stored_notes(app, patient_id) == [None]
    assert page.locator(MODAL).count() == 0 and dialogs == [] and errors == []
