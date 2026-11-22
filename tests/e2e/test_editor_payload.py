"""E2E test of the PDF editor: checks the payload the browser sends on save against the golden."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.aliases import SeedData
from tests.constants import EMAILS, TEST_PASSWORD
from tests.e2e import classic_editor_driver, scenario
from tests.e2e.conftest import DESKTOP_VIEWPORT

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_editor_payload_on_desktop(live_server: str, seed: SeedData, page: Page) -> None:
    """Run the click scenario on the desktop viewport and compare the saved payload with the golden.

    Run with "pytest -m e2e"; GOLDEN_RECORD=1 re-records the golden, only for an approved behavior change.

    :param live_server: Base URL of the running test server.
    :param seed: Ids of the fake records.
    :param page: Playwright page.
    """
    classic_editor_driver.login(page, live_server, EMAILS["admin"], TEST_PASSWORD)
    classic_editor_driver.open_editor(page, live_server, seed["diet_a4"])

    result = scenario.run_scenario(page, classic_editor_driver)

    assert len(result["payload"]["annotations"]) == len(scenario.CLICKS)
    assert len(result["chips"]) == len(scenario.CLICKS)
    scenario.record_or_compare(DESKTOP_VIEWPORT, result)
