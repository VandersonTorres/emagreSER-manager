"""Helpers of the patient page tests: what a browser would submit from the HTML of a page, and row snapshots."""

from collections.abc import Iterable
from typing import Any

from bs4 import BeautifulSoup, Tag

NON_SUBMITTED_INPUT_TYPES = {"submit", "button", "image", "reset", "file"}
CHECKABLE_INPUT_TYPES = {"checkbox", "radio"}


def _select_value(select: Tag) -> str:
    """Read the value a browser submits for a select: the selected option, or the first one when none is selected.

    :param select: The select element.
    :return: The value of the option, or an empty string when the select has no option.
    """
    options = select.find_all("option")
    chosen = next((option for option in options if option.has_attr("selected")), options[0] if options else None)
    if chosen is None:
        return ""
    return str(chosen.get("value", chosen.get_text()))


def _textarea_value(textarea: Tag) -> str:
    """Read the value a browser submits for a textarea: the text without the line break that follows the opening tag.

    :param textarea: The textarea element.
    :return: The text of the element, without one leading line break (``\\n`` or ``\\r\\n``).
    """
    text = textarea.get_text()
    for prefix in ("\r\n", "\n"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def form_entries(html: str, selector: str) -> list[tuple[str, str]]:
    """List the name and value pairs a browser submits for a form, before any script runs.

    Controls without a name, disabled ones, buttons, files and unchecked checkboxes or radios are left out.

    :param html: HTML of the page.
    :param selector: CSS selector of the form.
    :return: The pairs in document order.
    :raises AssertionError: If the form is not in the page.
    """
    form = BeautifulSoup(html, "html.parser").select_one(selector)
    assert form is not None, f"form {selector} not found"
    entries: list[tuple[str, str]] = []
    for control in form.find_all(["input", "select", "textarea"]):
        name = control.get("name")
        if not name or control.has_attr("disabled"):
            continue
        if control.name == "input":
            kind = str(control.get("type", "text")).lower()
            if kind in NON_SUBMITTED_INPUT_TYPES or (kind in CHECKABLE_INPUT_TYPES and not control.has_attr("checked")):
                continue
            entries.append((str(name), str(control.get("value", ""))))
        elif control.name == "select":
            entries.append((str(name), _select_value(control)))
        else:
            entries.append((str(name), _textarea_value(control)))
    return entries


def form_names(html: str, selector: str) -> list[str]:
    """List the names a browser submits for a form, sorted.

    :param html: HTML of the page.
    :param selector: CSS selector of the form.
    :return: The sorted names.
    """
    return sorted(name for name, _ in form_entries(html, selector))


def row_values(row: Any, columns: Iterable[str]) -> dict[str, Any]:
    """Snapshot some columns of a row as JSON friendly values, keeping numbers and text and turning dates into text.

    :param row: Model instance.
    :param columns: Names of the columns to read.
    :return: The column values by name.
    """
    snapshot: dict[str, Any] = {}
    for column in columns:
        value = getattr(row, column)
        snapshot[column] = value if isinstance(value, (int, float, str, type(None))) else str(value)
    return snapshot


def changed_columns(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """List the columns whose value changed between two snapshots.

    :param before: Snapshot taken before.
    :param after: Snapshot taken after.
    :return: The changed columns as {column: [before, after]}.
    """
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}
