"""Driver for the responsive editor DOM in app/templates/admin/diets/edit_diet.html and app/static/js/pdf_editor.js.

It exposes the interface of classic_editor_driver (login, open_editor, canvas_metrics, open_add_dialog, add_text,
next_page, record_chips, save), so the click script and the golden comparison of scenario.py run unchanged, plus
helpers for zoom, drag and the panels. Positions are always expressed in reference pixels of the page content box.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from tests.e2e.classic_editor_driver import login

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

__all__ = [
    "login",
    "open_editor",
    "canvas_metrics",
    "locate_point",
    "open_add_dialog",
    "add_text",
    "next_page",
    "record_chips",
    "save",
    "zoom_in",
    "is_touch",
    "chip_center",
    "drag_chip",
    "tap_chip",
]

EDITOR_URL = "/diets-manager/diets/edit_diet/{diet_id}"
SAVE_URL_GLOB = "**/diets-manager/diets/edit_diet/*"
RESULT_PDF_URL = "https://fixtures.test/diet-a4.pdf"
RENDER_TIMEOUT_MS = 60_000
DRAG_STEPS = 10

_FRAME = "#pdfe-frame"
_READY = "#pdfe-root[data-state=ready] #pdfe-frame[data-state=ready]"


def open_editor(page: Page, base_url: str, diet_id: int | str, total_pages: int = 2) -> None:
    """Open the diet editor and wait until the first page is painted ("Página 1 de N").

    pdf.js comes from a CDN, hence the long render timeout.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param diet_id: Id of the diet to edit.
    :param total_pages: Number of pages of the PDF, used to detect the end of the first render.
    """
    page.goto(base_url + EDITOR_URL.format(diet_id=diet_id))
    page.wait_for_selector(_READY, timeout=RENDER_TIMEOUT_MS)
    page.wait_for_function(
        "(total) => document.getElementById('pdfe-page-info').textContent.includes('de ' + total)",
        arg=total_pages,
        timeout=RENDER_TIMEOUT_MS,
    )


def canvas_metrics(page: Page) -> dict[str, float]:
    """Measure the page currently displayed.

    :param page: Playwright page.
    :return: Dict with the reference size (width, height), the displayed content box (clientWidth, clientHeight) and
        clientLeft and clientTop, always 0 because the page has no border.
    """
    return page.evaluate(
        """() => {
            const f = document.getElementById('pdfe-frame');
            const r = f.getBoundingClientRect();
            return {
                width: Number(f.dataset.canvasWidth), height: Number(f.dataset.canvasHeight),
                clientWidth: r.width, clientHeight: r.height, clientLeft: 0, clientTop: 0,
            };
        }"""
    )


def is_touch(page: Page) -> bool:
    """Tell whether the page runs in a touch context, where taps and touch drags replace the mouse.

    :param page: Playwright page.
    :return: True when the browser reports touch points.
    """
    return bool(page.evaluate("() => navigator.maxTouchPoints > 0"))


def locate_point(page: Page, fx: float, fy: float) -> dict[str, float]:
    """Scroll a page point to the center of the screen and return its viewport coordinates.

    fx and fy are fractions of the reference grid without the 1px border the first editor drew around its canvas, which
    is the area the CLICKS script was written for, so every editor is clicked at the same place of the sheet. The stage
    scrolls sideways and the window scrolls vertically; the point is measured again afterwards.

    :param page: Playwright page.
    :param fx: Horizontal fraction (0 to 1) of the page content box.
    :param fy: Vertical fraction (0 to 1) of the page content box.
    :return: Dict with the x and y viewport coordinates in CSS pixels.
    """
    script = """([fx, fy, scroll]) => {
        const f = document.getElementById('pdfe-frame');
        const stage = document.getElementById('pdfe-stage');
        const gw = Number(f.dataset.canvasWidth), gh = Number(f.dataset.canvasHeight);
        const point = () => {
            const r = f.getBoundingClientRect();
            return {
                x: r.left + (fx * (gw - 1) * r.width) / gw,
                y: r.top + (fy * (gh - 1) * r.height) / gh,
            };
        };
        if (scroll) {
            const p = point();
            const s = stage.getBoundingClientRect();
            stage.scrollLeft += p.x - (s.left + s.width / 2);
            window.scrollBy({top: p.y - window.innerHeight / 2, behavior: 'instant'});
        }
        return point();
    }"""
    page.evaluate(script, [fx, fy, True])
    return page.evaluate(script, [fx, fy, False])


def _tap(page: Page, x: float, y: float) -> None:
    """Tap (touch context) or click (mouse context) a viewport point.

    :param page: Playwright page.
    :param x: Horizontal viewport coordinate.
    :param y: Vertical viewport coordinate.
    """
    if is_touch(page):
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)


def open_add_dialog(page: Page, fx: float, fy: float) -> None:
    """Scroll to a page point, click or tap it and wait until the text panel is open with the text field focused.

    The editor focuses the text field synchronously; the wait is for exactly that state, so typing never races it.

    :param page: Playwright page.
    :param fx: Horizontal fraction (0 to 1) of the page content box.
    :param fy: Vertical fraction (0 to 1) of the page content box.
    """
    point = locate_point(page, fx, fy)
    _tap(page, point["x"], point["y"])
    page.wait_for_selector("#pdfe-panel[data-mode=add]", state="visible")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'pdfe-text'")


def add_text(page: Page, text: str, size: int, color: str) -> None:
    """Fill the open text panel and confirm it.

    :param page: Playwright page.
    :param text: Text to add.
    :param size: Font size.
    :param color: Text color as a hex string.
    """
    page.fill("#pdfe-text", text)
    page.fill("#pdfe-size", str(size))
    page.fill("#pdfe-color", color)
    page.click("#pdfe-submit")
    page.wait_for_selector("#pdfe-panel", state="hidden")


def next_page(page: Page) -> None:
    """Go to the next page and wait until it is painted.

    :param page: Playwright page.
    """
    before = page.text_content("#pdfe-page-info")
    page.click("#pdfe-next")
    page.wait_for_function(
        "(before) => document.getElementById('pdfe-page-info').textContent !== before"
        " && document.getElementById('pdfe-frame').dataset.state === 'ready'",
        arg=before,
        timeout=RENDER_TIMEOUT_MS,
    )


def zoom_in(page: Page, steps: int = 1) -> None:
    """Click the zoom in button and wait until the page is painted at the new size.

    :param page: Playwright page.
    :param steps: Number of zoom levels to go up.
    """
    for _ in range(steps):
        before = page.text_content("#pdfe-zoom-level")
        page.click("#pdfe-zoom-in")
        page.wait_for_function(
            "(before) => document.getElementById('pdfe-zoom-level').textContent !== before"
            " && document.getElementById('pdfe-frame').dataset.state === 'ready'",
            arg=before,
            timeout=RENDER_TIMEOUT_MS,
        )


def record_chips(page: Page) -> list[dict[str, Any]]:
    """Record the added texts (chips) of the displayed page, with rectangles in reference pixels of the content box.

    Screen pixels are multiplied by canvasWidth / contentWidth, so the values compare with the first editor's golden.

    :param page: Playwright page.
    :return: List of dicts with page, text, left, top, width and height (rounded to 2 decimals).
    """
    chips = page.evaluate(
        """() => {
            const f = document.getElementById('pdfe-frame');
            const r = f.getBoundingClientRect();
            const kx = Number(f.dataset.canvasWidth) / r.width;
            const ky = Number(f.dataset.canvasHeight) / r.height;
            return [...document.querySelectorAll('.pdfe-chip')].map((el) => {
                const b = el.getBoundingClientRect();
                return {
                    page: parseInt(el.dataset.page, 10), text: el.innerText,
                    left: (b.left - r.left) * kx, top: (b.top - r.top) * ky,
                    width: b.width * kx, height: b.height * ky,
                };
            });
        }"""
    )
    return [{**chip, **{k: round(chip[k], 2) for k in ("left", "top", "width", "height")}} for chip in chips]


def chip_center(page: Page, text: str) -> dict[str, float]:
    """Scroll a text into view and return the viewport coordinates of its center.

    :param page: Playwright page.
    :param text: Text of the chip.
    :return: Dict with the x and y viewport coordinates in CSS pixels.
    """
    return page.evaluate(
        """(text) => {
            const el = [...document.querySelectorAll('.pdfe-chip')].find((c) => c.innerText === text);
            const stage = document.getElementById('pdfe-stage');
            const locate = () => el.getBoundingClientRect();
            let b = locate();
            const s = stage.getBoundingClientRect();
            stage.scrollLeft += b.left + b.width / 2 - (s.left + s.width / 2);
            window.scrollBy({top: b.top + b.height / 2 - window.innerHeight / 2, behavior: 'instant'});
            b = locate();
            return {x: b.left + b.width / 2, y: b.top + b.height / 2};
        }""",
        text,
    )


def tap_chip(page: Page, text: str) -> None:
    """Click or tap a text and wait until its edit panel is open with the text field focused.

    :param page: Playwright page.
    :param text: Text of the chip.
    """
    point = chip_center(page, text)
    _tap(page, point["x"], point["y"])
    page.wait_for_selector("#pdfe-panel[data-mode=edit]", state="visible")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'pdfe-text'")


def drag_chip(page: Page, text: str, dx: float, dy: float) -> None:
    """Drag a text by a screen distance with the mouse, or with real touch events in a touch context.

    :param page: Playwright page.
    :param text: Text of the chip.
    :param dx: Horizontal distance in CSS pixels.
    :param dy: Vertical distance in CSS pixels.
    """
    start = chip_center(page, text)
    if not is_touch(page):
        page.mouse.move(start["x"], start["y"])
        page.mouse.down()
        page.mouse.move(start["x"] + dx, start["y"] + dy, steps=DRAG_STEPS)
        page.mouse.up()
        return
    session = page.context.new_cdp_session(page)
    try:
        session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [start]})
        for step in range(1, DRAG_STEPS + 1):
            point = {"x": start["x"] + dx * step / DRAG_STEPS, "y": start["y"] + dy * step / DRAG_STEPS}
            session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        session.detach()


def save(page: Page) -> dict[str, Any]:
    """Click save with the POST intercepted (nothing is stored) and return the payload exactly as sent.

    The intercepted answer is a success pointing at the fixture PDF, so the result panel renders as in production. The
    editor stays on the page; the panel is left open.

    :param page: Playwright page.
    :return: The JSON payload of the intercepted POST.
    :raises AssertionError: If the editor does not send exactly one POST.
    """
    captured: list[dict[str, Any]] = []

    def handler(route: Route) -> None:
        """Capture the POST payload and answer with a fake success; let other requests through.

        :param route: Playwright route of the intercepted request.
        """
        request = route.request
        if request.method == "POST":
            captured.append(request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"status": "success", "message": "ok", "redirect_url": "/", "download_url": RESULT_PDF_URL}
                ),
            )
        else:
            route.continue_()

    page.route(SAVE_URL_GLOB, handler)
    try:
        with page.expect_response(lambda r: r.request.method == "POST" and "/edit_diet/" in r.url):
            page.click("#pdfe-save")
        page.wait_for_selector("#pdfe-result[open] .pdfv[data-state=ready]", timeout=RENDER_TIMEOUT_MS)
    finally:
        page.unroute(SAVE_URL_GLOB, handler)
    assert len(captured) == 1, "the editor should send exactly one POST"
    return captured[0]
