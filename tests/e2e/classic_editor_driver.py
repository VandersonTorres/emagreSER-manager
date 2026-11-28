"""Driver for the editor DOM in app/templates/admin/diets/edit_diet.html and app/static/js/pdf_editor.js."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

EDITOR_URL = "/diets-manager/diets/edit_diet/{diet_id}?legacy=1"
SAVE_URL_GLOB = "**/diets-manager/diets/edit_diet/*"
RENDER_TIMEOUT_MS = 60_000


def login(page: Page, base_url: str, email: str, password: str) -> None:
    """Log in through the real /login page (Flask-Security).

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param email: Email of the user.
    :param password: Password of the user.
    """
    page.goto(f"{base_url}/login")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", password)
    page.click("form.login-form button[type=submit]")
    page.wait_for_url(f"{base_url}/")


def open_editor(page: Page, base_url: str, diet_id: int | str, total_pages: int = 2) -> None:
    """Open the diet editor and wait until pdf.js renders page 1 ("Página 1 de N").

    pdf.js comes from a CDN, hence the long render timeout.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param diet_id: Id of the diet to edit.
    :param total_pages: Number of pages of the PDF, used to detect the end of the first render.
    """
    page.goto(base_url + EDITOR_URL.format(diet_id=diet_id))
    page.wait_for_function(
        "(total) => document.getElementById('page-info').textContent.includes('de ' + total)",
        arg=total_pages,
        timeout=RENDER_TIMEOUT_MS,
    )


def canvas_metrics(page: Page) -> dict[str, float]:
    """Measure the canvas of the page currently displayed.

    :param page: Playwright page.
    :return: Dict with the canvas width, height, clientWidth, clientHeight, clientLeft and clientTop.
    """
    return page.evaluate(
        """() => {
            const c = document.getElementById('pdf-canvas');
            return {
                width: c.width, height: c.height,
                clientWidth: c.clientWidth, clientHeight: c.clientHeight,
                clientLeft: c.clientLeft, clientTop: c.clientTop,
            };
        }"""
    )


def _content_point(page: Page, fx: float, fy: float) -> dict[str, float]:
    """Convert fractions of the canvas content box (without the 1px border) into viewport coordinates.

    :param page: Playwright page.
    :param fx: Horizontal fraction (0 to 1) of the canvas content box.
    :param fy: Vertical fraction (0 to 1) of the canvas content box.
    :return: Dict with the x and y viewport coordinates in CSS pixels.
    """
    return page.evaluate(
        """([fx, fy]) => {
            const c = document.getElementById('pdf-canvas');
            const r = c.getBoundingClientRect();
            return {
                x: r.left + c.clientLeft + fx * c.clientWidth,
                y: r.top + c.clientTop + fy * c.clientHeight,
            };
        }""",
        [fx, fy],
    )


def open_add_dialog(page: Page, fx: float, fy: float) -> None:
    """Scroll to a canvas point, click it and wait until the text dialog is open and focused.

    The canvas is tall (about 1380px), so the page is scrolled first and the point is measured again afterwards. The
    editor focuses the text field one animation frame later; typing before that lets it steal the caret from a field.

    :param page: Playwright page.
    :param fx: Horizontal fraction (0 to 1) of the canvas content box.
    :param fy: Vertical fraction (0 to 1) of the canvas content box.
    """
    point = _content_point(page, fx, fy)
    page.evaluate("(y) => window.scrollBy(0, y - window.innerHeight / 2)", point["y"])
    point = _content_point(page, fx, fy)
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#text-modal", state="visible")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'text-input'")


def add_text(page: Page, text: str, size: int, color: str) -> None:
    """Fill the open text dialog and confirm it.

    :param page: Playwright page.
    :param text: Text to add.
    :param size: Font size.
    :param color: Text color as a hex string.
    """
    page.fill("#text-input", text)
    page.fill("#text-size", str(size))
    page.fill("#text-color", color)
    page.click("#add-text-btn")
    page.wait_for_selector("#text-modal", state="hidden")


def next_page(page: Page) -> None:
    """Go to the next page and wait until pdf.js finishes rendering it.

    :param page: Playwright page.
    """
    before = page.text_content("#page-info")
    page.click("#next-page")
    page.wait_for_function(
        "(before) => document.getElementById('page-info').textContent !== before", arg=before, timeout=RENDER_TIMEOUT_MS
    )


def record_chips(page: Page) -> list[dict[str, Any]]:
    """Record the added texts (chips) of the displayed page, with rectangles relative to the canvas content box.

    :param page: Playwright page.
    :return: List of dicts with page, text, left, top, width and height (rounded to 2 decimals).
    """
    chips = page.evaluate(
        """() => {
            const c = document.getElementById('pdf-canvas');
            const r = c.getBoundingClientRect();
            const ox = r.left + c.clientLeft, oy = r.top + c.clientTop;
            return [...document.querySelectorAll('.draggable-text')]
                .filter((el) => getComputedStyle(el).display !== 'none')
                .map((el) => {
                    const b = el.getBoundingClientRect();
                    return {
                        page: parseInt(el.dataset.page, 10), text: el.innerText,
                        left: b.left - ox, top: b.top - oy, width: b.width, height: b.height,
                    };
                });
        }"""
    )
    return [{**chip, **{k: round(chip[k], 2) for k in ("left", "top", "width", "height")}} for chip in chips]


def save(page: Page) -> dict[str, Any]:
    """Click save with the POST intercepted (nothing is stored) and return the payload exactly as sent.

    The editor calls alert()/confirm() (auto-dismissed by Playwright) and then navigates to the redirect_url.

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
                body=json.dumps({"status": "success", "message": "ok", "redirect_url": "/", "download_url": "/"}),
            )
        else:
            route.continue_()

    page.route(SAVE_URL_GLOB, handler)
    with page.expect_response(lambda r: r.request.method == "POST" and "/edit_diet/" in r.url):
        page.click("#save-changes-btn")
    page.wait_for_url(lambda url: "/edit_diet/" not in url, wait_until="commit")
    assert len(captured) == 1, "the editor should send exactly one POST"
    return captured[0]
