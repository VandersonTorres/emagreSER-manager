"""Fixtures for the e2e tests: live server in a thread and a Playwright browser."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import pytest
from flask import Flask

from tests.pdf_fixtures import SIZES, make_pdf

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Route, ViewportSize

DESKTOP_VIEWPORT: ViewportSize = {"width": 1366, "height": 900}
MOBILE_VIEWPORT: ViewportSize = {"width": 390, "height": 844}
DEFAULT_TIMEOUT_MS = 30_000


@pytest.fixture(scope="session")
def live_server(app: Flask) -> Iterator[str]:
    """Serve the test app (temporary SQLite) with werkzeug in a thread.

    :param app: Flask application.
    :return: The base URL of the running server (yielded; the server is shut down afterwards).
    """
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """Launch a headless Chromium-based browser for the session.

    E2E_BROWSER_CHANNEL (default "chrome") picks the Playwright channel; "chromium" uses the bundled Chromium (CI).
    Playwright is imported here, not at module level, so the default suite does not need it. A missing install errors
    instead of skipping, so the e2e step can never pass without checking the editor.

    :return: The Playwright browser (yielded; it is closed afterwards).
    """
    from playwright.sync_api import sync_playwright

    channel = os.environ.get("E2E_BROWSER_CHANNEL", "chrome")
    with sync_playwright() as playwright:
        if channel == "chromium":
            instance = playwright.chromium.launch(headless=True)
        else:
            instance = playwright.chromium.launch(channel=channel, headless=True)
        yield instance
        instance.close()


def _fulfill_fixture_pdf(pdf_bytes: bytes) -> Callable[[Route], None]:
    """Build a route handler that answers requests with a PDF and permissive CORS headers.

    :param pdf_bytes: PDF returned for every non-OPTIONS request.
    :return: The Playwright route handler.
    """
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "*",
    }

    def handler(route: Route) -> None:
        """Answer a routed request: 204 for CORS preflight, the PDF otherwise.

        :param route: Playwright route of the intercepted request.
        """
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=cors)
        else:
            route.fulfill(status=200, body=pdf_bytes, headers={"Content-Type": "application/pdf", **cors})

    return handler


@pytest.fixture
def context(browser: Browser) -> Iterator[BrowserContext]:
    """Create a desktop browser context (1366x900, scale 1) that serves the synthetic A4 PDF.

    Every request to https://fixtures.test/** is answered by the test itself, so nothing depends on external storage.
    The tests need internet for the pdf.js, jQuery and select2 CDNs.

    :param browser: Playwright browser.
    :return: The browser context (yielded; it is closed afterwards).
    """
    ctx = browser.new_context(viewport=DESKTOP_VIEWPORT, device_scale_factor=1)
    ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
    ctx.route("https://fixtures.test/**", _fulfill_fixture_pdf(make_pdf(*SIZES["a4_596x842"])))
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Open a new page in the browser context.

    :param context: Playwright browser context.
    :return: The new Playwright page.
    """
    return context.new_page()


@pytest.fixture
def mobile_context(browser: Browser) -> Iterator[BrowserContext]:
    """Create a phone browser context (390x844, touch) that serves the synthetic A4 PDF.

    :param browser: Playwright browser.
    :return: The browser context (yielded; it is closed afterwards).
    """
    ctx = browser.new_context(viewport=MOBILE_VIEWPORT, device_scale_factor=1, is_mobile=True, has_touch=True)
    ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
    ctx.route("https://fixtures.test/**", _fulfill_fixture_pdf(make_pdf(*SIZES["a4_596x842"])))
    yield ctx
    ctx.close()


@pytest.fixture
def mobile_page(mobile_context: BrowserContext) -> Page:
    """Open a new page in the phone context.

    :param mobile_context: Playwright phone browser context.
    :return: The new Playwright page.
    """
    return mobile_context.new_page()


@pytest.fixture(params=["desktop", "mobile"])
def device(request: pytest.FixtureRequest) -> tuple[str, Page]:
    """Provide a page for each viewport: desktop 1366x900 and phone 390x844.

    :param request: Pytest request, whose param is the viewport name.
    :return: The viewport name and the Playwright page.
    """
    page = request.getfixturevalue("page" if request.param == "desktop" else "mobile_page")
    return request.param, page
