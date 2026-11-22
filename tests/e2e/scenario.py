"""Editor-independent click scenario: the clicks, how they run and how the result is compared with the golden."""

from __future__ import annotations

import json
from types import ModuleType
from typing import TYPE_CHECKING, Any

from tests.golden_utils import dump_lines, load_golden, recording, unified_diff, write_golden

if TYPE_CHECKING:
    from playwright.sync_api import Page, ViewportSize

GOLDEN_NAME = "payload_desktop.json"
POSITION_TOLERANCE_PX = 1

CLICKS: list[dict[str, Any]] = [
    {"page": 1, "fx": 0.06, "fy": 0.05, "text": "Topo esq", "size": 9, "color": "#000000"},
    {"page": 1, "fx": 0.55, "fy": 0.20, "text": "Almoço 12h", "size": 12, "color": "#ff0000"},
    {"page": 1, "fx": 0.18, "fy": 0.38, "text": "Café da manhã", "size": 16, "color": "#1a7f37"},
    {"page": 1, "fx": 0.93, "fy": 0.52, "text": "Dir", "size": 12, "color": "#0000ff"},
    {"page": 1, "fx": 0.40, "fy": 0.72, "text": "Jantar", "size": 9, "color": "#8a2be2"},
    {"page": 1, "fx": 0.10, "fy": 0.96, "text": "Rodapé", "size": 20, "color": "#000000"},
    {"page": 2, "fx": 0.50, "fy": 0.15, "text": "João pág 2", "size": 12, "color": "#ff8800"},
    {"page": 2, "fx": 0.88, "fy": 0.92, "text": "Fim", "size": 9, "color": "#008080"},
]


def run_scenario(page: Page, driver: ModuleType) -> dict[str, Any]:
    """Run the CLICKS script with an editor driver and return what was measured.

    The editor must be open on page 1. fx/fy are fractions of the canvas content box, spaced so that a click never
    lands on a text already added. Texts of other pages are hidden, so chips are recorded page by page.

    :param page: Playwright page with the editor open.
    :param driver: Module exposing the editor driver interface (see classic_editor_driver).
    :return: Dict with the canvas metrics, the clicks, the saved payload and the recorded chips.
    """
    canvas = {"page1": driver.canvas_metrics(page)}
    chips = []
    pages = sorted({click["page"] for click in CLICKS})
    for number in pages:
        if number > 1:
            driver.next_page(page)
            canvas[f"page{number}"] = driver.canvas_metrics(page)
        for click in (c for c in CLICKS if c["page"] == number):
            driver.open_add_dialog(page, click["fx"], click["fy"])
            driver.add_text(page, click["text"], click["size"], click["color"])
        chips.extend(driver.record_chips(page))
    payload = driver.save(page)
    return {"canvas": canvas, "clicks": CLICKS, "payload": payload, "chips": chips}


def build_golden(viewport: ViewportSize, result: dict[str, Any]) -> dict[str, Any]:
    """Assemble the golden structure from a scenario result.

    :param viewport: Browser viewport the scenario ran in.
    :param result: Result returned by run_scenario.
    :return: The golden dictionary.
    """
    return {
        "viewport": viewport,
        "canvas": result["canvas"],
        "clicks": result["clicks"],
        "payload": result["payload"],
        "chips": result["chips"],
    }


def dump_golden(golden: dict[str, Any]) -> str:
    """Serialize the golden as JSON with one item per line, for readable git diffs.

    :param golden: Golden dictionary built by build_golden.
    :return: The JSON text.
    :raises AssertionError: If the payload has a key other than "annotations".
    """
    assert set(golden["payload"]) == {"annotations"}, "the payload has a new key; update dump_golden"
    canvas = ",\n".join(f"    {json.dumps(key)}: {json.dumps(value)}" for key, value in golden["canvas"].items())
    return (
        "{\n"
        f'  "viewport": {json.dumps(golden["viewport"])},\n'
        f'  "canvas": {{\n{canvas}\n  }},\n'
        f'  "clicks": {dump_lines(golden["clicks"], 2)},\n'
        f'  "payload": {{\n    "annotations": {dump_lines(golden["payload"]["annotations"], 4)}\n  }},\n'
        f'  "chips": {dump_lines(golden["chips"], 2)}\n'
        "}\n"
    )


def compare_with_golden(viewport: ViewportSize, result: dict[str, Any]) -> None:
    """Compare a scenario result with the golden.

    Order, texts, fontSize, color, page and canvas size must be identical. The payload x/y and the chips left/top
    accept a 1px tolerance, because the chip width and height depend on the fonts.

    :param viewport: Browser viewport the scenario ran in.
    :param result: Result returned by run_scenario.
    :raises AssertionError: If the editor calibration differs from the golden.
    """
    golden = load_golden(GOLDEN_NAME)
    assert golden["viewport"] == viewport
    assert golden["clicks"] == json.loads(json.dumps(result["clicks"])), "the CLICKS script changed"

    expected = golden["payload"]["annotations"]
    actual = result["payload"]["annotations"]
    assert [a["text"] for a in actual] == [a["text"] for a in expected], "payload texts or order changed"
    errors = []
    for index, (exp, act) in enumerate(zip(expected, actual)):
        for field in ("text", "fontSize", "color", "page", "canvasWidth", "canvasHeight"):
            if exp[field] != act[field]:
                errors.append(f"[{index}] {exp['text']!r}: {field} {exp[field]!r} -> {act[field]!r}")
        for field in ("x", "y"):
            if abs(exp[field] - act[field]) > POSITION_TOLERANCE_PX:
                errors.append(f"[{index}] {exp['text']!r}: {field} {exp[field]} -> {act[field]} (tolerance 1px)")
    assert set(golden["payload"]) == set(result["payload"]), "payload keys changed"

    chips_expected = golden["chips"]
    chips_actual = result["chips"]
    assert [(c["page"], c["text"]) for c in chips_actual] == [(c["page"], c["text"]) for c in chips_expected]
    for exp, act in zip(chips_expected, chips_actual):
        for field in ("left", "top"):
            if abs(exp[field] - act[field]) > POSITION_TOLERANCE_PX:
                errors.append(f"chip {exp['text']!r}: {field} {exp[field]} -> {act[field]} (tolerance 1px)")

    if errors:
        diff = unified_diff(
            dump_lines(expected, 0), dump_lines(actual, 0), from_label="golden payload", to_label="current payload"
        )
        raise AssertionError("The editor calibration changed:\n" + "\n".join(errors) + "\n" + diff)


def record_or_compare(viewport: ViewportSize, result: dict[str, Any]) -> None:
    """Record the golden when recording is enabled, otherwise compare with it.

    :param viewport: Browser viewport the scenario ran in.
    :param result: Result returned by run_scenario.
    :raises AssertionError: If comparing and the editor calibration differs from the golden.
    """
    if recording():
        write_golden(GOLDEN_NAME, dump_golden(build_golden(viewport, result)))
    else:
        compare_with_golden(viewport, result)
