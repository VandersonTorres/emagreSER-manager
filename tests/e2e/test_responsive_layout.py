"""E2E tests of the responsive shell: no horizontal overflow, mobile drawer, desktop sidebar and review screenshots.

Set SCREENSHOT_DIR to a folder to also save one PNG per page and viewport; without it nothing is written.
"""

from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flask import Flask, url_for

from tests.aliases import SeedData
from tests.constants import EMAILS, NUTRITIONIST_USERNAME, TEST_PASSWORD
from tests.e2e import classic_editor_driver

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

SCREENSHOT_ENV = "SCREENSHOT_DIR"
OPEN_MENU = "Abrir menu de navegação"
CLOSE_MENU = "Fechar menu de navegação"
SHOWN_CLASS = re.compile(r"(^|\s)show(\s|$)")
KNOWN_PAGE_ERRORS: set[str] = set()


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


def test_backup_page_fits_the_screen_and_downloads_the_archive(
    app: Flask, live_server: str, device: tuple[str, Page], set_superusers: Callable[[str], None]
) -> None:
    """Check the backup page of a superuser on both viewports: menu entry, no sideways scroll and a real download.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param set_superusers: Function that sets the superuser e-mails.
    """
    from playwright.sync_api import expect

    device_name, page = device
    set_superusers(EMAILS["admin"])
    _login(page, live_server, "admin")
    page.goto(live_server + _url(app, "backup.show_backup"))
    _settle(page)

    expect(page.get_by_role("heading", name="Backup do banco de dados", level=1)).to_be_visible()
    button = page.get_by_role("button", name="Baixar backup")
    expect(button).to_be_visible()
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], metrics
    _snap(page, device_name, "backup")

    sidebar = page.locator("#app-sidebar")
    if device_name == "mobile":
        page.get_by_role("button", name=OPEN_MENU).click()
        page.wait_for_function("() => !document.querySelector('#app-sidebar').classList.contains('showing')")
    expect(sidebar.get_by_role("link", name="Backup")).to_be_visible()
    expect(sidebar.locator("a[aria-current=page]")).to_have_text(re.compile(r"Backup"))
    _snap(page, device_name, "backup-menu")
    if device_name == "mobile":
        page.get_by_role("button", name=CLOSE_MENU).click()
        expect(sidebar).to_be_hidden()

    with page.expect_download() as download_info:
        button.click()
    download = download_info.value
    assert re.fullmatch(r"emagreser-backup-\d{4}-\d{2}-\d{2}_\d{4}\.zip", download.suggested_filename)
    assert zipfile.is_zipfile(download.path())


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
    "endpoint, fragment",
    [
        ("patients.view_patient", "#avaliacoes"),
        ("patients.view_patient", "#bioimpedancia"),
        ("schedules.list_schedules", ""),
        ("specialists.list_specialists", ""),
        ("admin.list_users", ""),
    ],
)
def test_wide_tables_end_inside_the_card_or_scroll_inside_it(
    app: Flask, seed: SeedData, live_server: str, page: Page, endpoint: str, fragment: str, width: int
) -> None:
    """Check that no table of a page is cut by the card edge.

    Every table must either end inside the card or sit in a scroll container that ends inside the card, so no action
    column is hidden out of reach whatever the fonts of the machine. The patient record shows one table per tab, so
    each tab is opened through its URL hash.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param endpoint: Endpoint of the page under test.
    :param fragment: URL hash that opens the tab of the patient record, empty for the other pages.
    :param width: Viewport width in pixels.
    """
    values = {"id": int(seed["patient_nutritionist"])} if endpoint == "patients.view_patient" else {}
    page.set_viewport_size({"width": width, "height": 900})
    _login(page, live_server, "admin")
    page.goto(live_server + _url(app, endpoint, **values) + fragment)
    _settle(page)
    if fragment:
        page.wait_for_selector(f"{fragment.replace('#', '#pane-')}.active")

    tables = page.evaluate(TABLES_FIT_SCRIPT)

    assert tables, endpoint
    for table in tables:
        fits = table["right"] <= table["cardRight"] + 1
        scroller_fits = table["scrollerRight"] is not None and table["scrollerRight"] <= table["cardRight"] + 1
        assert fits or (table["scrolls"] and scroller_fits), (endpoint, fragment, width, table)


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
        Screen("patients-list", "admin", _url(app, "patients.list_patients"), ready=".patient-item"),
        Screen("patient-view", "admin", _url(app, "patients.view_patient", id=patient), ready=".patient-header"),
        Screen("patient-add", "admin", _url(app, "patients.add_patient"), ready="form.add-patient-form"),
        Screen("patient-edit", "admin", _url(app, "patients.edit_patient", id=patient), ready="form.edit-patient-form"),
        Screen(
            "patient-history",
            "admin",
            _url(app, "patients.view_custom_history", id=patient, pat_name="Paciente Teste 1"),
            ready="canvas#evolutionsChart",
        ),
        Screen("patient-delete", "admin", _url(app, "patients.delete_patient", id=patient), ready=".confirm-card"),
        Screen(
            "anthro-add",
            "admin",
            _url(app, "patients.add_anthro", patient_id=patient),
            ready="form.add-anthro-form",
        ),
        Screen(
            "anthro-edit",
            "admin",
            _url(app, "patients.edit_anthro", patient_id=patient, evaluation_id=int(seed["anthro"])),
            ready="form.edit-anthro-form",
        ),
        Screen(
            "skinfold-add",
            "admin",
            _url(app, "patients.add_skinfold", patient_id=patient),
            ready="form.add-skinfold-form",
        ),
        Screen(
            "skinfold-edit",
            "admin",
            _url(app, "patients.edit_skinfold", patient_id=patient, skinfold_id=int(seed["skinfold"])),
            ready="form.edit-skinfold-form",
        ),
        Screen("diets-list", "admin", _url(app, "diets.list_diets"), ready="#diet-list .diet-handle"),
        Screen("diets-search", "admin", _url(app, "diets.list_diets", query="Teste"), ready=".diet-reorder-hint"),
        Screen("diet-add", "admin", _url(app, "diets.add_diet"), ready="form.add-diet-form"),
        Screen(
            "diet-edit", "admin", _url(app, "diets.edit_diet_raw", id=int(seed["diet_a4"])), ready="form.edit-diet-form"
        ),
        Screen(
            "diet-delete",
            "admin",
            _url(app, "diets.delete_diet", id=int(seed["diet_backend"])),
            ready="form.delete-diet-form",
        ),
        Screen("schedules-list", "admin", _url(app, "schedules.list_schedules"), ready="section.schedule-card"),
        Screen(
            "schedules-day",
            "admin",
            _url(app, "schedules.list_schedules", date=str(seed["schedule_future_date"])),
            ready=".schedule-filter-summary",
        ),
        Screen("schedule-action", "admin", _url(app, "schedules.schedule_action"), ready=".select2-container"),
        Screen("specialists-list", "admin", _url(app, "specialists.list_specialists"), ready="table.record-table"),
        Screen("specialist-add", "admin", _url(app, "specialists.add_specialist"), ready="form.add-specialist-form"),
        Screen(
            "specialist-edit",
            "admin",
            _url(app, "specialists.edit_specialist", id=int(seed["specialist_other"])),
            ready="form.edit-specialist-form",
        ),
        Screen("users-list", "admin", _url(app, "admin.list_users"), ready="table.record-table"),
        Screen("user-add", "admin", _url(app, "admin.create_user"), ready="form.create-user-form"),
        Screen(
            "user-delete",
            "admin",
            _url(app, "admin.delete_user", id=int(seed["user_secretary"])),
            ready="form.delete-user-form",
        ),
    ]
    return anonymous, admin


def _open(page: Page, base_url: str, screen: Screen, device_name: str, errors: list[str]) -> None:
    """Open a screen, check its status and key element, and save its screenshot.

    :param page: Playwright page.
    :param base_url: Base URL of the running server.
    :param screen: Page to open.
    :param device_name: Viewport name.
    :param errors: List that collects the uncaught JavaScript errors of the page; the ones in KNOWN_PAGE_ERRORS are
        ignored.
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
    assert page.locator("link[href$='/css/legacy.css']").count() == 1
    assert page.locator("link[href*='bootstrap']").count() == 0
    _snap(page, device_name, "diet-editor")

    page.context.clear_cookies()
    _login(page, live_server, "nutritionist")
    _open(
        page, live_server, Screen("home-nutritionist", "nutritionist", "/", ready=".shortcut-tile"), device_name, errors
    )
