"""E2E tests of the responsive diet editor: calibration at every screen size, drag, panels, save and result panel."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import fitz
import pytest
from flask import Flask, url_for

from tests import backend_helpers
from tests.aliases import ClientFactory, SeedData
from tests.constants import EMAILS, TEST_PASSWORD
from tests.e2e import editor_driver, scenario
from tests.e2e.conftest import DEFAULT_TIMEOUT_MS, DESKTOP_VIEWPORT, _fulfill_fixture_pdf
from tests.golden_utils import load_golden
from tests.pdf_fixtures import SIZES, make_pdf

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Dialog, Page, Route, ViewportSize

pytestmark = pytest.mark.e2e

PHONE_VIEWPORT: ViewportSize = {"width": 390, "height": 844}
WINDOW_900_VIEWPORT: ViewportSize = {"width": 900, "height": 900}
DESKTOP_TOLERANCE_PX = 1
SMALL_SCREEN_TOLERANCE_PX = 3
PDF_TOLERANCE_PT = 1
PAYLOAD_KEYS = ["text", "x", "y", "fontSize", "color", "page", "canvasWidth", "canvasHeight"]
RGB_PATTERN = re.compile(r"^rgb\(\d{1,3}, \d{1,3}, \d{1,3}\)$")
MIXED_SIZES_PAGE_2 = (488, 1371)
MIXED_PDF_PAGES = ((596, 842), (298, 836))


def _context(browser: Browser, pdf: bytes, **options: Any) -> Iterator[BrowserContext]:
    """Create a browser context that serves a synthetic PDF for every fixtures.test request.

    :param browser: Playwright browser.
    :param pdf: PDF served for https://fixtures.test/**.
    :param options: Extra arguments of Browser.new_context.
    :return: The browser context (yielded; it is closed afterwards).
    """
    ctx = browser.new_context(**options)
    ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
    ctx.route("https://fixtures.test/**", _fulfill_fixture_pdf(pdf))
    yield ctx
    ctx.close()


@pytest.fixture
def phone_page(browser: Browser) -> Iterator[Page]:
    """Open a page in a phone context: 390x844, device scale factor 3, touch.

    :param browser: Playwright browser.
    :return: The Playwright page (yielded; its context is closed afterwards).
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    for ctx in _context(browser, pdf, viewport=PHONE_VIEWPORT, device_scale_factor=3, is_mobile=True, has_touch=True):
        yield ctx.new_page()


@pytest.fixture
def window_900_page(browser: Browser) -> Iterator[Page]:
    """Open a page in a 900x900 desktop window (mouse, the sidebar is the mobile drawer).

    :param browser: Playwright browser.
    :return: The Playwright page (yielded; its context is closed afterwards).
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    for ctx in _context(browser, pdf, viewport=WINDOW_900_VIEWPORT, device_scale_factor=1):
        yield ctx.new_page()


@pytest.fixture
def mixed_sizes_page(browser: Browser) -> Iterator[Page]:
    """Open a desktop page whose PDF has an A4 first page and a 298x836 second page.

    :param browser: Playwright browser.
    :return: The Playwright page (yielded; its context is closed afterwards).
    """
    doc = fitz.open()
    for width, height in MIXED_PDF_PAGES:
        doc.new_page(width=width, height=height)
    pdf = doc.tobytes()
    doc.close()
    for ctx in _context(browser, pdf, viewport=DESKTOP_VIEWPORT, device_scale_factor=1):
        yield ctx.new_page()


def _open(page: Page, live_server: str, seed: SeedData, diet: str = "diet_a4") -> None:
    """Log in as admin and open the editor of a diet.

    :param page: Playwright page.
    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param diet: Seed key of the diet to edit.
    """
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    editor_driver.open_editor(page, live_server, seed[diet])


def _view_path(endpoint: str, diet_id: int) -> str:
    """Build the path of a diet view page.

    :param endpoint: Endpoint of the view ("diets.view_diet" or "diets.view_last_edition").
    :param diet_id: Id of the diet.
    :return: The URL path.
    """
    return {
        "diets.view_diet": f"/diets-manager/diets/{diet_id}",
        "diets.view_last_edition": f"/diets-manager/diets/view_edited{diet_id}",
    }[endpoint]


def _add(page: Page, text: str, fx: float, fy: float, size: int = 12, color: str = "#000000") -> None:
    """Add a text at a point of the page.

    :param page: Playwright page.
    :param text: Text to add.
    :param fx: Horizontal fraction of the page content box.
    :param fy: Vertical fraction of the page content box.
    :param size: Font size.
    :param color: Text color as a hex string.
    """
    editor_driver.open_add_dialog(page, fx, fy)
    editor_driver.add_text(page, text, size, color)


def _save_and_continue(page: Page) -> list[dict[str, Any]]:
    """Save with the request intercepted, close the result panel and return the annotations sent.

    :param page: Playwright page.
    :return: The annotations of the payload.
    """
    payload = editor_driver.save(page)
    page.click("#pdfe-result-continue")
    page.wait_for_selector("#pdfe-result", state="hidden")
    return payload["annotations"]


def _collect_dialogs(page: Page) -> list[str]:
    """Record the messages of the JavaScript dialogs (alert, confirm, prompt) the page opens, dismissing them.

    :param page: Playwright page.
    :return: The list that receives the messages.
    """
    messages: list[str] = []

    def handler(dialog: Dialog) -> None:
        """Store the message of a dialog and dismiss it.

        :param dialog: Playwright dialog.
        """
        messages.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handler)
    return messages


def test_desktop_payload_matches_the_golden(live_server: str, seed: SeedData, page: Page) -> None:
    """Run the click script on the desktop viewport and compare the payload and the chips with the golden.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)

    result = scenario.run_scenario(page, editor_driver)

    assert len(result["payload"]["annotations"]) == len(scenario.CLICKS)
    assert len(result["chips"]) == len(scenario.CLICKS)
    scenario.compare_with_golden(DESKTOP_VIEWPORT, result)
    assert result["canvas"]["page1"]["clientWidth"] == 977


def test_phone_payload_stays_within_the_tolerance(live_server: str, seed: SeedData, phone_page: Page) -> None:
    """Tap the click script on a 390x844 phone (device scale factor 3) and compare with the desktop golden.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param phone_page: Playwright page of the phone context.
    """
    _open(phone_page, live_server, seed)

    result = scenario.run_scenario(phone_page, editor_driver)

    scenario.compare_within_tolerance(result, SMALL_SCREEN_TOLERANCE_PX)
    assert result["canvas"]["page1"]["clientWidth"] < 390


def test_narrow_window_payload_stays_within_the_tolerance(
    live_server: str, seed: SeedData, window_900_page: Page
) -> None:
    """Click the script in a 900x900 window and compare with the desktop golden.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param window_900_page: Playwright page of the 900x900 context.
    """
    _open(window_900_page, live_server, seed)

    result = scenario.run_scenario(window_900_page, editor_driver)

    scenario.compare_within_tolerance(result, SMALL_SCREEN_TOLERANCE_PX)
    assert result["canvas"]["page1"]["clientWidth"] < 977


def test_zoomed_in_payload_stays_within_one_pixel(live_server: str, seed: SeedData, page: Page) -> None:
    """Zoom in two steps on the desktop and click the script, comparing with the golden at the desktop tolerance.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    editor_driver.zoom_in(page, steps=2)

    result = scenario.run_scenario(page, editor_driver)

    scenario.compare_within_tolerance(result, DESKTOP_TOLERANCE_PX)
    assert result["canvas"]["page1"]["clientWidth"] == pytest.approx(977 * 1.5, abs=1)


def test_zoom_buttons_fit_and_limits(live_server: str, seed: SeedData, page: Page) -> None:
    """Check the zoom label, the fit button and the disabled state of the zoom buttons at the ends.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)

    assert page.text_content("#pdfe-zoom-level") == "100%"
    assert page.is_disabled("#pdfe-zoom-fit")
    editor_driver.zoom_in(page, steps=4)
    assert page.text_content("#pdfe-zoom-level") == "300%"
    assert page.is_disabled("#pdfe-zoom-in")
    page.click("#pdfe-zoom-fit")
    page.wait_for_function("() => document.getElementById('pdfe-zoom-level').textContent === '100%'")
    assert page.is_disabled("#pdfe-zoom-fit")
    assert editor_driver.canvas_metrics(page)["clientWidth"] == 977


def _annotation(annotations: list[dict[str, Any]], text: str) -> dict[str, Any]:
    """Find an annotation of a payload by its text.

    :param annotations: Annotations of a payload.
    :param text: Text to look for.
    :return: The annotation.
    """
    return next(annotation for annotation in annotations if annotation["text"] == text)


def _drag_scenario(page: Page, dx: float, dy: float, tolerance: float) -> None:
    """Add three texts, drag the second by a screen distance and check the payload before and after.

    :param page: Playwright page with the editor open.
    :param dx: Horizontal drag distance in CSS pixels.
    :param dy: Vertical drag distance in CSS pixels.
    :param tolerance: Largest accepted difference, in reference pixels, between the drag and the screen distance.
    """
    _add(page, "Um", 0.20, 0.20)
    _add(page, "Dois", 0.50, 0.50)
    _add(page, "Tres", 0.30, 0.75)
    metrics = editor_driver.canvas_metrics(page)
    before = _save_and_continue(page)

    editor_driver.drag_chip(page, "Dois", dx, dy)
    after = _save_and_continue(page)

    assert [a["text"] for a in after] == [a["text"] for a in before] == ["Um", "Dois", "Tres"]
    moved_x = _annotation(after, "Dois")["x"] - _annotation(before, "Dois")["x"]
    moved_y = _annotation(after, "Dois")["y"] - _annotation(before, "Dois")["y"]
    assert moved_x == pytest.approx(dx * metrics["width"] / metrics["clientWidth"], abs=tolerance)
    assert moved_y == pytest.approx(dy * metrics["height"] / metrics["clientHeight"], abs=tolerance)
    for text in ("Um", "Tres"):
        assert _annotation(after, text) == _annotation(before, text)


def test_mouse_drag_moves_by_the_screen_distance(live_server: str, seed: SeedData, page: Page) -> None:
    """Drag a text with the mouse on the desktop: it moves by the screen distance and the order does not change.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)

    _drag_scenario(page, dx=120, dy=-80, tolerance=DESKTOP_TOLERANCE_PX)


def test_touch_drag_moves_by_the_screen_distance(live_server: str, seed: SeedData, phone_page: Page) -> None:
    """Drag a text with real touch events on the phone: it moves by the screen distance and the order is kept.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param phone_page: Playwright page of the phone context.
    """
    _open(phone_page, live_server, seed)

    _drag_scenario(phone_page, dx=-60, dy=45, tolerance=SMALL_SCREEN_TOLERANCE_PX)


def test_press_without_movement_opens_the_edit_panel_and_does_not_drag(
    live_server: str, seed: SeedData, page: Page
) -> None:
    """Click a text without moving: the edit panel opens and the position stays the same.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    _add(page, "Parado", 0.40, 0.40)
    before = _save_and_continue(page)

    editor_driver.tap_chip(page, "Parado")
    page.click("#pdfe-cancel")
    after = _save_and_continue(page)

    assert after == before


def test_each_annotation_carries_the_canvas_size_of_its_own_page(
    live_server: str, seed: SeedData, mixed_sizes_page: Page
) -> None:
    """Use a PDF with an A4 page and a 298x836 page: every annotation gets the reference size of its own page.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param mixed_sizes_page: Playwright page whose PDF has pages of different sizes.
    """
    _open(mixed_sizes_page, live_server, seed)
    _add(mixed_sizes_page, "Pagina 1", 0.50, 0.50)
    editor_driver.next_page(mixed_sizes_page)
    metrics = editor_driver.canvas_metrics(mixed_sizes_page)
    _add(mixed_sizes_page, "Pagina 2", 0.50, 0.50)

    payload = editor_driver.save(mixed_sizes_page)["annotations"]

    assert (metrics["width"], metrics["height"]) == MIXED_SIZES_PAGE_2
    assert [(a["page"], a["canvasWidth"], a["canvasHeight"]) for a in payload] == [
        (1, 977, 1380),
        (2, *MIXED_SIZES_PAGE_2),
    ]
    page_2 = _annotation(payload, "Pagina 2")
    assert page_2["x"] == pytest.approx(0.5 * (MIXED_SIZES_PAGE_2[0] - 1) + 1, abs=DESKTOP_TOLERANCE_PX)
    assert page_2["y"] == pytest.approx(0.5 * (MIXED_SIZES_PAGE_2[1] - 1) + 1, abs=DESKTOP_TOLERANCE_PX)


def test_payload_shape_and_types(live_server: str, seed: SeedData, page: Page) -> None:
    """Check the exact keys, their order and the types of the annotations, and the rgb() color format.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    _add(page, "Forma", 0.30, 0.30, size=16, color="#1a7f37")

    payload = editor_driver.save(page)

    assert list(payload) == ["annotations"]
    (annotation,) = payload["annotations"]
    assert list(annotation) == PAYLOAD_KEYS
    assert annotation["text"] == "Forma"
    assert isinstance(annotation["x"], (int, float)) and isinstance(annotation["y"], (int, float))
    assert isinstance(annotation["fontSize"], int) and annotation["fontSize"] == 16
    assert RGB_PATTERN.match(annotation["color"]) and annotation["color"] == "rgb(26, 127, 55)"
    assert annotation["page"] == 1 and isinstance(annotation["page"], int)
    assert annotation["canvasWidth"] == 977 and annotation["canvasHeight"] == 1380


def test_empty_text_adds_nothing_and_escape_cancels(live_server: str, seed: SeedData, page: Page) -> None:
    """Confirm an empty (or blank) text and press Escape on a typed one: nothing is added in either case.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)

    _add(page, "", 0.30, 0.30)
    _add(page, "     ", 0.40, 0.40)
    editor_driver.open_add_dialog(page, 0.50, 0.50)
    page.fill("#pdfe-text", "Cancelado")
    page.keyboard.press("Escape")
    page.wait_for_selector("#pdfe-panel", state="hidden")
    editor_driver.open_add_dialog(page, 0.60, 0.60)
    page.keyboard.press("Enter")
    page.wait_for_selector("#pdfe-panel", state="hidden")

    assert editor_driver.record_chips(page) == []


def test_enter_adds_the_text(live_server: str, seed: SeedData, page: Page) -> None:
    """Type a text and press Enter in the field: the text is added.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)

    editor_driver.open_add_dialog(page, 0.30, 0.30)
    page.keyboard.type("Via Enter")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pdfe-panel", state="hidden")

    assert [chip["text"] for chip in editor_driver.record_chips(page)] == ["Via Enter"]


def test_text_field_is_focused_as_soon_as_the_panel_opens(live_server: str, seed: SeedData, page: Page) -> None:
    """Type right after the panel opens, without any wait: every character lands in the text field.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    point = editor_driver.locate_point(page, 0.30, 0.30)

    page.mouse.click(point["x"], point["y"])
    page.keyboard.type("Digitado de imediato")

    assert page.input_value("#pdfe-text") == "Digitado de imediato"
    assert page.input_value("#pdfe-size") == "9"


def test_edit_panel_keeps_the_color_and_edits_remove_and_nudge(live_server: str, seed: SeedData, page: Page) -> None:
    """Open the edit panel of a colored text, change it, nudge it by 1 reference pixel and remove another one.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    _add(page, "Verde", 0.30, 0.30, size=16, color="#1a7f37")
    _add(page, "Sobra", 0.30, 0.60, size=12, color="#ff0000")
    before = {a["text"]: a for a in _save_and_continue(page)}

    editor_driver.tap_chip(page, "Verde")
    assert page.input_value("#pdfe-text") == "Verde"
    assert page.input_value("#pdfe-size") == "16"
    assert page.input_value("#pdfe-color") == "#1a7f37"
    for _ in range(3):
        page.click("#pdfe-nudge-right")
    page.click("#pdfe-nudge-down")
    page.fill("#pdfe-text", "Verde 2")
    page.fill("#pdfe-size", "18")
    page.fill("#pdfe-color", "#0000ff")
    page.click("#pdfe-submit")
    page.wait_for_selector("#pdfe-panel", state="hidden")
    editor_driver.tap_chip(page, "Sobra")
    page.click("#pdfe-remove")
    page.wait_for_selector("#pdfe-panel", state="hidden")
    after = _save_and_continue(page)

    assert [a["text"] for a in after] == ["Verde 2"]
    edited = after[0]
    assert edited["x"] == pytest.approx(before["Verde"]["x"] + 3)
    assert edited["y"] == pytest.approx(before["Verde"]["y"] + 1)
    assert (edited["fontSize"], edited["color"]) == (18, "rgb(0, 0, 255)")


def test_keyboard_enter_on_a_chip_opens_the_edit_panel(live_server: str, seed: SeedData, page: Page) -> None:
    """Focus a text with the keyboard and press Enter: the edit panel opens and stays open with the field focused.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    _add(page, "Teclado", 0.30, 0.30, size=14, color="#ff8800")

    page.focus(".pdfe-chip")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pdfe-panel[data-mode=edit]", state="visible")

    assert page.evaluate("() => document.activeElement.id") == "pdfe-text"
    assert page.input_value("#pdfe-text") == "Teclado"
    assert page.input_value("#pdfe-size") == "14"
    assert page.get_attribute(".pdfe-chip", "role") == "button"
    page.keyboard.press("Escape")
    page.wait_for_selector("#pdfe-panel", state="hidden")
    assert page.evaluate("() => document.activeElement.classList.contains('pdfe-chip')")


def test_shared_viewer_is_sharp_and_changes_pages(live_server: str, seed: SeedData, phone_page: Page) -> None:
    """Open the edited diet on the phone: the bitmap has the device resolution and the page buttons work.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param phone_page: Playwright page of the phone context.
    """
    editor_driver.login(phone_page, live_server, EMAILS["admin"], TEST_PASSWORD)
    phone_page.goto(live_server + _view_path("diets.view_last_edition", int(seed["diet_edited"])))
    phone_page.wait_for_selector(".pdfv[data-state=ready]", timeout=editor_driver.RENDER_TIMEOUT_MS)

    shown = phone_page.evaluate("() => document.querySelector('.pdfv-canvas').getBoundingClientRect().width")
    bitmap = phone_page.evaluate("() => document.querySelector('.pdfv-canvas').width")
    assert bitmap == pytest.approx(shown * 3, abs=2)
    assert phone_page.text_content(".pdfv-info") == "Página 1 de 2"
    assert phone_page.is_disabled("button[aria-label='Página anterior']")

    phone_page.click("button[aria-label='Próxima página']")
    phone_page.wait_for_function("() => document.querySelector('.pdfv').dataset.page === '2'")
    assert phone_page.text_content(".pdfv-info") == "Página 2 de 2"
    assert phone_page.is_disabled("button[aria-label='Próxima página']")


@pytest.mark.parametrize(
    ("endpoint", "root", "message"),
    [
        (None, "#pdfe-root[data-state=error]", "editor antigo"),
        ("diets.view_last_edition", ".pdfv[data-state=error]", "Atualize a página e tente novamente"),
    ],
)
def test_blocked_pdfjs_shows_the_load_error(
    live_server: str, seed: SeedData, page: Page, endpoint: str | None, root: str, message: str
) -> None:
    """Block pdf.js: the editor and the viewer leave the loading state, show their message and raise no page error.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    :param endpoint: View endpoint to open, or None for the editor.
    :param root: Selector of the root element once it reports the error.
    :param message: Text the user must read in the status line.
    """
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/pdf.min.js", lambda route: route.abort())
    editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    if endpoint is None:
        page.goto(live_server + editor_driver.EDITOR_URL.format(diet_id=seed["diet_a4"]))
        status = "#pdfe-status"
    else:
        page.goto(live_server + _view_path(endpoint, int(seed["diet_edited"])))
        status = ".pdfv-status"

    page.wait_for_selector(root)

    assert message in page.text_content(status)
    assert "Carregando" not in page.text_content(status)
    assert errors == []


def test_chips_belong_to_their_page(live_server: str, seed: SeedData, page: Page) -> None:
    """Only the texts of the current page are shown, and they come back when returning to the page.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    _add(page, "Primeira", 0.30, 0.30)
    editor_driver.next_page(page)
    assert editor_driver.record_chips(page) == []
    _add(page, "Segunda", 0.30, 0.30)

    page.click("#pdfe-prev")
    page.wait_for_function("() => document.getElementById('pdfe-page-info').textContent.includes('Página 1')")

    assert [(c["page"], c["text"]) for c in editor_driver.record_chips(page)] == [(1, "Primeira")]


def test_panel_placement_on_desktop_and_phone(live_server: str, seed: SeedData, page: Page, phone_page: Page) -> None:
    """The panel floats next to the clicked point on the desktop and is a bottom sheet on the phone.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    :param phone_page: Playwright page of the phone context.
    """
    _open(page, live_server, seed)
    point = editor_driver.locate_point(page, 0.50, 0.50)
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#pdfe-panel", state="visible")
    box = page.locator("#pdfe-panel").bounding_box()
    assert box is not None
    assert box["y"] + box["height"] <= point["y"]
    assert box["x"] <= point["x"] <= box["x"] + box["width"]
    assert box["width"] < 400

    _open(phone_page, live_server, seed)
    editor_driver.open_add_dialog(phone_page, 0.50, 0.50)
    sheet = phone_page.locator("#pdfe-panel").bounding_box()
    assert sheet is not None
    assert sheet["x"] == 0 and sheet["width"] == PHONE_VIEWPORT["width"]
    assert sheet["y"] + sheet["height"] == pytest.approx(PHONE_VIEWPORT["height"], abs=1)
    overflow = phone_page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0


def test_phone_page_is_sharp_and_controls_are_touch_sized(live_server: str, seed: SeedData, phone_page: Page) -> None:
    """The bitmap has the device resolution, touch is allowed on the page, and the controls are at least 44px.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param phone_page: Playwright page of the phone context.
    """
    _open(phone_page, live_server, seed)
    _add(phone_page, "Toque", 0.50, 0.50)

    measured = phone_page.evaluate(
        """() => {
            const frame = document.getElementById('pdfe-frame');
            const canvas = document.getElementById('pdfe-canvas');
            const chip = document.querySelector('.pdfe-chip');
            const buttons = [...document.querySelectorAll('.pdfe-toolbar button')].map((b) => {
                const r = b.getBoundingClientRect();
                return {id: b.id, width: r.width, height: r.height, label: b.getAttribute('aria-label')};
            });
            return {
                bitmap: canvas.width, shown: frame.getBoundingClientRect().width,
                frameTouch: getComputedStyle(frame).touchAction, chipTouch: getComputedStyle(chip).touchAction,
                buttons,
            };
        }"""
    )

    assert measured["bitmap"] == pytest.approx(measured["shown"] * 3, abs=2)
    assert measured["frameTouch"] in ("manipulation", "pan-x pan-y pinch-zoom")
    assert measured["chipTouch"] == "none"
    assert len(measured["buttons"]) >= 6
    for button in measured["buttons"]:
        assert button["label"], button
        assert button["width"] >= 44 and button["height"] >= 44, button


@pytest.mark.parametrize("width", [320, 600, 768, 1024])
def test_editor_and_viewers_never_scroll_sideways(
    browser: Browser, live_server: str, seed: SeedData, width: int
) -> None:
    """Open the editor and both viewers at several window widths: the page never overflows and the sheet fits.

    :param browser: Playwright browser.
    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param width: Window width in CSS pixels.
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    for ctx in _context(browser, pdf, viewport={"width": width, "height": 800}, device_scale_factor=1):
        page = ctx.new_page()
        _open(page, live_server, seed)
        overflow = "() => document.documentElement.scrollWidth - window.innerWidth"
        assert page.evaluate(overflow) <= 0
        metrics = editor_driver.canvas_metrics(page)
        stage = page.locator("#pdfe-stage").bounding_box()
        assert stage is not None and metrics["clientWidth"] <= stage["width"]
        for endpoint, key in (("diets.view_diet", "diet_a4"), ("diets.view_last_edition", "diet_edited")):
            with ctx.new_page() as other:
                other.goto(live_server + _view_path(endpoint, int(seed[key])))
                other.wait_for_selector(".pdfv[data-state=ready]", timeout=editor_driver.RENDER_TIMEOUT_MS)
                assert other.evaluate(overflow) <= 0
                canvas = other.locator(".pdfv-canvas").bounding_box()
                assert canvas is not None and canvas["width"] <= width


def test_unsaved_changes_ask_before_leaving(live_server: str, seed: SeedData, page: Page) -> None:
    """The page asks before unloading only while there are changes that were not saved.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    probe = (
        "() => { const e = new Event('beforeunload', {cancelable: true});"
        " window.dispatchEvent(e); return e.defaultPrevented; }"
    )
    _open(page, live_server, seed)
    assert page.evaluate(probe) is False

    _add(page, "Pendente", 0.30, 0.30)
    assert page.evaluate(probe) is True

    editor_driver.save(page)
    assert page.evaluate(probe) is False
    page.click("#pdfe-result-continue")
    _add(page, "Mais um", 0.50, 0.50)
    assert page.evaluate(probe) is True


@pytest.fixture
def backend_pdf(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the server download the synthetic A4 PDF instead of reaching the network.

    :param app: Flask application, kept so the live server is the same process the patch applies to.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    monkeypatch.setattr("app.views.diets.requests.get", lambda url, *args, **kwargs: backend_helpers.FakeResponse(pdf))


@pytest.mark.usefixtures("backend_pdf")
def test_real_save_shows_the_result_panel_and_keeps_editing(
    app: Flask, live_server: str, seed: SeedData, page: Page
) -> None:
    """Save for real: the result panel renders the generated PDF, and "Continuar editando" keeps every text.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    dialogs = _collect_dialogs(page)
    _open(page, live_server, seed, diet="diet_backend")
    _add(page, "Salvo de verdade", 0.30, 0.30)
    _add(page, "Outro texto", 0.30, 0.60, color="#ff0000")

    page.click("#pdfe-save")
    page.wait_for_selector("#pdfe-result[open] .pdfv[data-state=ready]", timeout=editor_driver.RENDER_TIMEOUT_MS)

    with app.test_request_context():
        download = url_for("diets.download_temp_diet", filename=f"dieta_personalizada_id_{seed['diet_backend']}.pdf")
        home = url_for("diets.list_diets")
    assert page.get_attribute("#pdfe-result-download", "href") == download
    assert page.get_attribute("#pdfe-result-finish", "href") == home
    generated = page.request.get(live_server + download)
    with fitz.open(stream=generated.body(), filetype="pdf") as doc:
        text = doc[0].get_text()
    assert "Salvo de verdade" in text and "Outro texto" in text
    assert page.evaluate("() => document.querySelector('#pdfe-result canvas').width") > 0

    page.click("#pdfe-result-continue")
    page.wait_for_selector("#pdfe-result", state="hidden")
    assert [chip["text"] for chip in editor_driver.record_chips(page)] == ["Salvo de verdade", "Outro texto"]
    assert page.text_content("#pdfe-save-label") == "Salvar" and page.is_enabled("#pdfe-save")
    page.wait_for_selector("#pdfe-result .pdfv", state="detached")
    assert dialogs == []


def test_save_button_blocks_a_second_submit_while_saving(live_server: str, seed: SeedData, page: Page) -> None:
    """While the request is in flight the button is disabled and shows "Salvando...", and a second click sends nothing.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    held: list[Route] = []
    posts: list[str] = []

    def handler(route: Route) -> None:
        """Hold the save request until the test answers it; let other requests through.

        :param route: Playwright route of the intercepted request.
        """
        if route.request.method == "POST":
            posts.append(route.request.url)
            held.append(route)
        else:
            route.continue_()

    _open(page, live_server, seed)
    _add(page, "Aguarde", 0.30, 0.30)
    page.route(editor_driver.SAVE_URL_GLOB, handler)

    page.click("#pdfe-save")
    page.wait_for_function("() => document.getElementById('pdfe-save').disabled")
    page.evaluate("() => document.getElementById('pdfe-save').click()")

    assert page.text_content("#pdfe-save-label") == "Salvando..."
    assert page.get_attribute("#pdfe-save", "aria-busy") == "true"
    assert len(posts) == 1
    held[0].fulfill(status=200, content_type="application/json", body='{"status": "error", "message": "Falhou"}')
    page.wait_for_function("() => !document.getElementById('pdfe-save').disabled")
    assert len(posts) == 1


def test_save_error_is_shown_inline(live_server: str, seed: SeedData, page: Page) -> None:
    """A failed save shows the message of the server inline, with no alert, and the editor stays usable.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page of the desktop context.
    """
    dialogs = _collect_dialogs(page)

    def handler(route: Route) -> None:
        """Answer the save with a server error; let other requests through.

        :param route: Playwright route of the intercepted request.
        """
        if route.request.method == "POST":
            route.fulfill(
                status=500,
                content_type="application/json",
                body='{"status": "error", "message": "Erro ao atualizar o PDF"}',
            )
        else:
            route.continue_()

    _open(page, live_server, seed)
    page.click("#pdfe-save")
    assert "ao menos um texto" in page.text_content("#pdfe-feedback")
    _add(page, "Vai falhar", 0.30, 0.30)
    page.route(editor_driver.SAVE_URL_GLOB, handler)

    page.click("#pdfe-save")
    page.wait_for_function("() => document.getElementById('pdfe-feedback').textContent.includes('Erro ao atualizar')")

    assert page.is_enabled("#pdfe-save")
    assert page.locator("#pdfe-result[open]").count() == 0
    assert [chip["text"] for chip in editor_driver.record_chips(page)] == ["Vai falhar"]
    assert dialogs == []


def test_new_editor_pdf_matches_the_baseline_pdf(
    app: Flask,
    seed: SeedData,
    client_for: ClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    live_server: str,
    page: Page,
) -> None:
    """Generate the PDF from the new editor's desktop payload and from the golden payload: every text lands within 1pt.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param monkeypatch: pytest monkeypatch fixture.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    _open(page, live_server, seed)
    new_payload = scenario.run_scenario(page, editor_driver)["payload"]["annotations"]
    baseline_payload = load_golden(scenario.GOLDEN_NAME)["payload"]["annotations"]
    pdf = make_pdf(*SIZES["a4_596x842"])

    new_spans = backend_helpers.apply_annotations(app, seed, client_for, monkeypatch, pdf, new_payload)
    baseline_spans = backend_helpers.apply_annotations(app, seed, client_for, monkeypatch, pdf, baseline_payload)

    assert len(new_spans) == len(baseline_spans) == len(scenario.CLICKS)
    for new, baseline in zip(new_spans, baseline_spans):
        assert (new["page"], new["text"]) == (baseline["page"], baseline["text"])
        for key in ("origin", "bbox"):
            for new_value, baseline_value in zip(new[key], baseline[key]):
                assert abs(new_value - baseline_value) <= PDF_TOLERANCE_PT, (new["text"], key, new, baseline)
