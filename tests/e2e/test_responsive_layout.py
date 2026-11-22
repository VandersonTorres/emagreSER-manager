"""E2E tests of the responsive shell: no horizontal overflow, mobile drawer, desktop sidebar and review screenshots.

Set SCREENSHOT_DIR to a folder to also save one PNG per page and viewport; without it nothing is written.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flask import Flask, url_for

from tests.aliases import SeedData
from tests.constants import EMAILS, NUTRITIONIST_USERNAME, TEST_PASSWORD
from tests.e2e import classic_editor_driver
from tests.e2e.conftest import DEFAULT_TIMEOUT_MS, _fulfill_fixture_pdf
from tests.pdf_fixtures import SIZES, make_pdf

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, ViewportSize

pytestmark = pytest.mark.e2e

MOBILE_VIEWPORT: ViewportSize = {"width": 390, "height": 844}
SCREENSHOT_ENV = "SCREENSHOT_DIR"
OPEN_MENU = "Abrir menu de navegação"
CLOSE_MENU = "Fechar menu de navegação"
SHOWN_CLASS = re.compile(r"(^|\s)show(\s|$)")
KNOWN_PAGE_ERRORS = {"patients is not defined"}


@dataclass(frozen=True)
class Screen:
    """A page to open and photograph for the visual review.

    :param name: File name stem of the screenshot.
    :param role: Role to log in as before opening the page, or None for an anonymous visitor.
    :param path: URL path of the page.
    :param status: Expected HTTP status.
    :param ready: CSS selector that must be visible before the screenshot.
    """

    name: str
    role: str | None
    path: str
    status: int = 200
    ready: str = "main#main-content"


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


def _url(app: Flask, endpoint: str, **values: int | str) -> str:
    """Build a URL path outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


def _login(page: Page, base_url: str, role: str) -> None:
    """Log in through the real login page.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param role: Role whose fake user logs in.
    """
    classic_editor_driver.login(page, base_url, EMAILS[role], TEST_PASSWORD)


def _settle(page: Page) -> None:
    """Wait until the page, its stylesheets, scripts and fonts are loaded.

    :param page: Playwright page.
    """
    page.wait_for_load_state("load")
    page.evaluate("() => document.fonts.ready.then(() => true)")


def _snap(page: Page, device_name: str, name: str) -> None:
    """Save a full page screenshot when SCREENSHOT_DIR is set; do nothing otherwise.

    :param page: Playwright page.
    :param device_name: Viewport name, used as file name prefix.
    :param name: Screen name, used as file name stem.
    """
    folder = os.environ.get(SCREENSHOT_ENV)
    if not folder:
        return
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target / f"{device_name}-{name}.png"), full_page=True)


def _overflow(page: Page) -> dict[str, int]:
    """Measure the horizontal overflow of the page.

    :param page: Playwright page.
    :return: Dict with the document scrollWidth and the window innerWidth.
    """
    return page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, inner: window.innerWidth})",
    )


@pytest.mark.parametrize("page_name", ["login", "home", "change-password"])
def test_no_horizontal_overflow(live_server: str, device: tuple[str, Page], page_name: str) -> None:
    """Check that the main pages never scroll sideways on the desktop and phone viewports.

    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param page_name: Page under test.
    """
    _, page = device
    if page_name == "login":
        page.goto(f"{live_server}/login")
    else:
        _login(page, live_server, "admin")
        page.goto(f"{live_server}/" if page_name == "home" else f"{live_server}/change")
    _settle(page)

    metrics = _overflow(page)

    assert metrics["scroll"] <= metrics["inner"], metrics


def test_mobile_drawer_opens_and_navigates(live_server: str, mobile_page: Page) -> None:
    """Check that on a phone the menu button opens the drawer, a link navigates and the close button works.

    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    """
    from playwright.sync_api import expect

    _login(mobile_page, live_server, "admin")
    sidebar = mobile_page.locator("#app-sidebar")
    expect(sidebar).to_be_hidden()

    mobile_page.get_by_role("button", name=OPEN_MENU).click()
    expect(sidebar).to_be_visible()
    expect(sidebar).to_have_class(SHOWN_CLASS)
    mobile_page.get_by_role("button", name=CLOSE_MENU).click()
    expect(sidebar).to_be_hidden()

    mobile_page.get_by_role("button", name=OPEN_MENU).click()
    sidebar.get_by_role("link", name="Pacientes").click()
    mobile_page.wait_for_url(re.compile(r".*/patients-manager/patients$"))
    expect(mobile_page.get_by_role("heading", name="Pacientes", exact=True)).to_be_visible()
    expect(sidebar).to_be_hidden()


def test_desktop_sidebar_is_visible_without_toggling(live_server: str, page: Page) -> None:
    """Check that on a desktop the sidebar is always visible, without a menu button.

    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    _login(page, live_server, "admin")
    sidebar = page.locator("#app-sidebar")

    expect(sidebar).to_be_visible()
    expect(page.get_by_role("button", name=OPEN_MENU)).to_be_hidden()
    box = sidebar.bounding_box()
    assert box is not None and box["x"] == 0 and box["width"] >= 200
    sidebar.get_by_role("link", name="Pacientes").click()
    page.wait_for_url(re.compile(r".*/patients-manager/patients$"))
    expect(sidebar.locator("a[aria-current=page]")).to_have_text(re.compile(r"Pacientes"))


def test_toast_is_visible_and_can_be_dismissed(live_server: str, device: tuple[str, Page]) -> None:
    """Check that a flashed message appears as a toast on both viewports and the close button removes it.

    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    device_name, page = device
    _login(page, live_server, "nutritionist")
    page.goto(f"{live_server}/specialists-manager/specialists")
    toast = page.locator("#toast-region .toast")

    expect(toast).to_have_count(1)
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("Acesso negado")
    _snap(page, device_name, "toast-danger")
    toast.get_by_role("button", name="Fechar aviso").click()
    expect(toast).to_have_count(0)


def test_info_toast_hides_itself(live_server: str, seed: SeedData, device: tuple[str, Page]) -> None:
    """Check that a non-critical toast shows up and then hides itself.

    Booking a time that conflicts with the seeded schedule flashes an info message and writes nothing.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    _, page = device
    _login(page, live_server, "admin")
    page.request.post(
        f"{live_server}/schedules-manager/schedule_action",
        form={
            "patient_id": str(seed["patient_schedule"]),
            "date_time": f"{seed['schedule_future_date']}T10:00",
            "specialist": NUTRITIONIST_USERNAME,
        },
        max_redirects=0,
    )
    page.goto(f"{live_server}/schedules-manager/schedules")
    toast = page.locator("#toast-region .toast")

    expect(toast).to_have_count(1)
    expect(toast).to_be_visible()
    expect(toast).to_have_attribute("role", "status")
    expect(toast).to_contain_text("já existe um agendamento")
    expect(toast).to_have_count(0, timeout=15_000)


WIDE_TABLE_WIDTHS = [1366, 1024, 900, 800]
TABLES_FIT_SCRIPT = """
() => {
    const card = document.querySelector('.app-content');
    const cardRight = card.getBoundingClientRect().right;
    const scroller = (table) => {
        for (let el = table; el && el !== card; el = el.parentElement) {
            if (['auto', 'scroll'].includes(getComputedStyle(el).overflowX)) return el;
        }
        return null;
    };
    return [...card.querySelectorAll('table')].map((table) => {
        const box = scroller(table);
        return {
            name: table.className,
            right: table.getBoundingClientRect().right,
            cardRight,
            scrollerRight: box ? box.getBoundingClientRect().right : null,
            scrolls: box ? box.scrollWidth > box.clientWidth : false,
        };
    });
}
"""


@pytest.mark.parametrize("width", WIDE_TABLE_WIDTHS)
@pytest.mark.parametrize(
    "endpoint", ["patients.view_patient", "schedules.list_schedules", "specialists.list_specialists"]
)
def test_wide_tables_end_inside_the_card_or_scroll_inside_it(
    app: Flask, seed: SeedData, live_server: str, page: Page, endpoint: str, width: int
) -> None:
    """Check that no table of a page shown in the compatibility layer is cut by the card edge.

    Every table must either end inside the card or sit in a scroll container that ends inside the card, so no action
    column is hidden out of reach whatever the fonts of the machine.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param endpoint: Endpoint of the page under test.
    :param width: Viewport width in pixels.
    """
    values = {"id": int(seed["patient_nutritionist"])} if endpoint == "patients.view_patient" else {}
    page.set_viewport_size({"width": width, "height": 900})
    _login(page, live_server, "admin")
    page.goto(live_server + _url(app, endpoint, **values))
    _settle(page)

    tables = page.evaluate(TABLES_FIT_SCRIPT)

    assert tables, endpoint
    for table in tables:
        fits = table["right"] <= table["cardRight"] + 1
        scroller_fits = table["scrollerRight"] is not None and table["scrollerRight"] <= table["cardRight"] + 1
        assert fits or (table["scrolls"] and scroller_fits), (endpoint, width, table)


def _screens(app: Flask, seed: SeedData) -> tuple[list[Screen], list[Screen]]:
    """Build the pages of the visual review.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The pages for an anonymous visitor and the pages for logged in users, in opening order.
    """
    patient = int(seed["patient_nutritionist"])
    anonymous = [
        Screen("login", None, "/login", ready="form.login-form"),
        Screen("403-anonymous", None, _url(app, "patients.list_patients"), status=403),
        Screen("404", None, "/this-page-does-not-exist", status=404),
    ]
    admin = [
        Screen("home-admin", "admin", "/", ready=".shortcut-tile"),
        Screen("change-password", "admin", "/change", ready="form.change-pass-form"),
        Screen("404-logged-in", "admin", "/this-page-does-not-exist", status=404),
        Screen("patients-list", "admin", _url(app, "patients.list_patients")),
        Screen("patient-view", "admin", _url(app, "patients.view_patient", id=patient), ready=".anthro-table"),
        Screen("patient-add", "admin", _url(app, "patients.add_patient"), ready="form.add-patient-form"),
        Screen("diets-list", "admin", _url(app, "diets.list_diets"), ready="#diet-list"),
        Screen("schedules-list", "admin", _url(app, "schedules.list_schedules")),
        Screen("schedule-action", "admin", _url(app, "schedules.schedule_action"), ready=".select2-container"),
        Screen("specialists-list", "admin", _url(app, "specialists.list_specialists")),
        Screen("users-list", "admin", _url(app, "admin.list_users")),
    ]
    return anonymous, admin


def _open(page: Page, base_url: str, screen: Screen, device_name: str, errors: list[str]) -> None:
    """Open a screen, check its status and key element, and save its screenshot.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param screen: Page to open.
    :param device_name: Viewport name.
    :param errors: List that collects the uncaught JavaScript errors of the page; the stray "patients" statement that
        list_patients.js already had is ignored through KNOWN_PAGE_ERRORS.
    """
    from playwright.sync_api import expect

    response = page.goto(base_url + screen.path)
    assert response is not None and response.status == screen.status, (screen.name, response and response.status)
    _settle(page)
    expect(page.locator(screen.ready).first).to_be_visible()
    unexpected = [error for error in errors if error not in KNOWN_PAGE_ERRORS]
    assert unexpected == [], (screen.name, unexpected)
    _snap(page, device_name, screen.name)


def test_review_screens(app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]) -> None:
    """Open every page of the review on both viewports, checking status codes and saving screenshots on demand.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    device_name, page = device
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    anonymous, admin = _screens(app, seed)

    for screen in anonymous:
        _open(page, live_server, screen, device_name, errors)

    _login(page, live_server, "admin")
    for screen in admin:
        _open(page, live_server, screen, device_name, errors)

    if device_name == "mobile":
        page.goto(f"{live_server}/")
        page.get_by_role("button", name=OPEN_MENU).click()
        expect(page.locator("#app-sidebar")).to_have_class(SHOWN_CLASS)
        expect(page.locator("#app-sidebar .nav-link").first).to_be_visible()
        page.wait_for_function("() => !document.querySelector('#app-sidebar').classList.contains('showing')")
        _snap(page, device_name, "drawer-open")

    classic_editor_driver.open_editor(page, live_server, seed["diet_a4"])
    assert page.locator("link[href*='legacy.css']").count() == 1
    assert page.locator("link[href*='bootstrap']").count() == 0
    _snap(page, device_name, "diet-editor")

    page.context.clear_cookies()
    _login(page, live_server, "nutritionist")
    _open(
        page, live_server, Screen("home-nutritionist", "nutritionist", "/", ready=".shortcut-tile"), device_name, errors
    )
