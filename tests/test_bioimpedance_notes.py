"""Observation of a bioimpedance measurement: the dialog of the record, the notes of the tab and the forms."""

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from flask import Flask, url_for
from flask.testing import FlaskClient

from app.models import AnthropometricEvaluation, db
from tests.aliases import ClientFactory
from tests.note_helpers import NOTE_BUTTON, NOTE_MODAL_ID, NOTE_TITLE, add_measurement
from tests.patient_cases import FIXED_EVALUATION

STATIC_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"
OLD_NOTE = "Paciente relatou dor no joelho."
NEW_NOTE = "Retorno em 15 dias.\nTrazer os exames de sangue."
HOSTILE_NOTE = "<script>alert(1)</script> <img src=x onerror=alert(2)> & \"aspas\" &amp; 'apóstrofo'"


def _record(app: Flask, client: FlaskClient, patient_id: int) -> BeautifulSoup:
    """Open the record of a patient, which must answer 200, and parse it.

    :param app: Flask application.
    :param client: Test client.
    :param patient_id: Id of the patient.
    :return: The parsed record.
    """
    with app.test_request_context():
        url = url_for("patients.view_patient", id=patient_id)
    response = client.get(url)
    assert response.status_code == 200, f"GET {url}: {response.status_code}"
    return BeautifulSoup(response.get_data(as_text=True), "html.parser")


def _modal_text(soup: BeautifulSoup) -> str | None:
    """Read the text of the observation dialog.

    :param soup: Parsed record.
    :return: The text of the note, or None when the page has no dialog.
    """
    text = soup.select_one(f"#{NOTE_MODAL_ID} .note-modal-text")
    return None if text is None else text.get_text()


@pytest.fixture
def patient_id(case_patients: Callable[..., int]) -> int:
    """Create a patient of the nutritionist without measurements.

    :param case_patients: Factory of temporary patients.
    :return: The id of the patient.
    """
    return case_patients("Paciente Observacoes", specialist="specialist_nutritionist")


def test_dialog_shows_the_date_and_the_text_of_the_latest_note(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check the dialog: title, date and text of the latest measurement, the "Entendi" button and its accessibility.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 3, 1), OLD_NOTE)
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    soup = _record(app, client_admin, patient_id)

    dialogs = soup.select(".modal")
    assert len(dialogs) == 1
    dialog = dialogs[0]
    assert dialog["id"] == NOTE_MODAL_ID and dialog["tabindex"] == "-1"
    title = dialog.select_one(".modal-title")
    assert title is not None and title.get_text(" ", strip=True) == NOTE_TITLE
    assert dialog["aria-labelledby"] == title["id"]
    text = dialog.select_one(".note-modal-text")
    assert text is not None and dialog["aria-describedby"] == text["id"]
    assert text.get_text() == NEW_NOTE
    moment = dialog.select_one(".note-modal-date time")
    assert moment is not None and moment["datetime"] == "2026-04-02" and moment.get_text() == "02/04/2026"
    assert "Bioimpedância de" in dialog.select_one(".note-modal-date").get_text()
    assert OLD_NOTE not in str(dialog)
    acknowledge = dialog.select_one(".modal-footer button")
    assert acknowledge is not None and acknowledge.get_text(strip=True) == NOTE_BUTTON
    assert "btn-primary" in acknowledge["class"] and acknowledge["data-bs-dismiss"] == "modal"
    close = dialog.select_one(".modal-header .btn-close")
    assert close is not None and close["data-bs-dismiss"] == "modal" and close["aria-label"] == "Fechar"
    assert dialog.select_one(".modal-dialog-scrollable") is not None


def test_return_focus_target_is_a_programmatically_focusable_heading(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check that the heading with the patient name can receive the focus when the dialog closes.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    heading = _record(app, client_admin, patient_id).select_one("h1#patient-name")

    assert heading is not None and heading["tabindex"] == "-1"


def test_dialog_comes_with_every_load_of_the_record(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that there is no "seen" state: the dialog is rendered each time the record is opened.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    first = _record(app, client_admin, patient_id)
    second = _record(app, client_admin, patient_id)

    assert _modal_text(first) == _modal_text(second) == NEW_NOTE


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_every_role_that_opens_the_record_sees_the_dialog(
    app: Flask, client_for: ClientFactory, patient_id: int, role: str
) -> None:
    """Check the dialog for the admin, the secretary and the nutritionist who owns the patient.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param patient_id: Id of a patient of the nutritionist.
    :param role: Role under test.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    soup = _record(app, client_for(role), patient_id)

    assert _modal_text(soup) == NEW_NOTE


def test_nutritionist_still_cannot_open_the_record_of_another_patient(
    app: Flask, client_nutritionist: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that the note does not open a way around the access rule of the record.

    :param app: Flask application.
    :param client_nutritionist: Test client logged in as nutritionist.
    :param case_patients: Factory of temporary patients.
    """
    other = case_patients("Paciente De Outro Profissional", specialist="specialist_other")
    add_measurement(app, other, date(2026, 4, 2), NEW_NOTE)
    with app.test_request_context():
        url = url_for("patients.view_patient", id=other)

    response = client_nutritionist.get(url)

    assert response.status_code == 302
    assert NEW_NOTE not in response.get_data(as_text=True)


def test_no_dialog_when_the_latest_measurement_has_no_note_even_if_an_older_one_has(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check that only the latest measurement counts: an older note does not open the dialog.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 3, 1), OLD_NOTE)
    add_measurement(app, patient_id, date(2026, 4, 2), None)

    soup = _record(app, client_admin, patient_id)

    assert soup.select(".modal") == [] and soup.select_one(f"#{NOTE_MODAL_ID}") is None
    assert OLD_NOTE in soup.select_one("#pane-bioimpedancia").get_text()


def test_no_dialog_without_measurements(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that a patient without bioimpedance gets no dialog.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    soup = _record(app, client_admin, patient_id)

    assert soup.select(".modal") == []


def test_no_dialog_when_the_latest_note_is_only_blanks(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that a note with nothing but blanks, written outside the forms, is treated as no note.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), " \n\t ")

    soup = _record(app, client_admin, patient_id)

    assert soup.select(".modal") == [] and soup.select(".skinfold-note-row") == []


@pytest.mark.parametrize(
    "rows, expected",
    [
        ([(date(2026, 5, 1), "A", 1), (date(2026, 5, 1), None, 2)], None),
        ([(date(2026, 5, 1), None, 1), (date(2026, 5, 1), "B", 2)], "B"),
        ([(date(2026, 5, 1), "A", 1), (date(2026, 5, 1), "B", 2)], "B"),
        ([(date(2026, 5, 1), "A", 2), (date(2026, 5, 1), "B", 1)], "A"),
        ([(date(2026, 6, 1), "Mais nova", 1), (date(2026, 5, 1), None, 2)], "Mais nova"),
        (
            [(date(2026, 5, 1), None, 1), (date(2026, 6, 1), "Mais nova", 2), (date(2026, 4, 1), "Velha", 3)],
            "Mais nova",
        ),
    ],
    ids=[
        "tie_higher_id_has_no_note",
        "tie_higher_id_has_the_note",
        "tie_both_have_a_note",
        "tie_the_note_of_the_higher_id_wins_when_inserted_first",
        "newer_date_wins_over_a_higher_id",
        "newest_date_among_three",
    ],
)
def test_latest_measurement_is_the_highest_date_then_the_highest_id(
    app: Flask,
    client_admin: FlaskClient,
    patient_id: int,
    rows: list[tuple[date, str | None, int]],
    expected: str | None,
) -> None:
    """Check which note opens the dialog: the one of the latest date and, on a tie, of the measurement saved last.

    The third value of each row is the order in which it is saved, so it sets the ids.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    :param rows: Measurements as (date, note, order of saving).
    :param expected: Text of the dialog, or None when there is no dialog.
    """
    for when, note, _ in sorted(rows, key=lambda row: row[2]):
        add_measurement(app, patient_id, when, note)

    assert _modal_text(_record(app, client_admin, patient_id)) == expected


def test_html_in_a_note_is_shown_as_text(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that a note with markup is escaped in the dialog and in the tab, and creates no element.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), HOSTILE_NOTE)

    with app.test_request_context():
        url = url_for("patients.view_patient", id=patient_id)
    html = client_admin.get(url).get_data(as_text=True)
    soup = BeautifulSoup(html, "html.parser")

    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert _modal_text(soup) == HOSTILE_NOTE
    assert soup.select_one(".skinfold-note-text").get_text() == HOSTILE_NOTE
    assert soup.select(f"#{NOTE_MODAL_ID} img, #{NOTE_MODAL_ID} script, #pane-bioimpedancia img") == []
    assert [script for script in soup.find_all("script") if "alert(" in script.get_text()] == []


def test_line_breaks_of_a_note_are_kept(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that the text reaches the page with its line breaks and that the styles keep them as line breaks.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    note = "primeira\nsegunda\n\nquarta"
    add_measurement(app, patient_id, date(2026, 4, 2), note)

    soup = _record(app, client_admin, patient_id)

    assert _modal_text(soup) == note
    assert soup.select_one(".skinfold-note-text").get_text() == note
    css = STATIC_CSS.read_text(encoding="utf-8")
    for selector in (".note-modal-text", ".skinfold-note-text"):
        block = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
        assert block is not None and "white-space: pre-line" in block.group(1), selector
        assert "overflow-wrap: anywhere" in block.group(1), selector


def _measurement_rows(soup: BeautifulSoup) -> list[Tag]:
    """List the rows of the measurement table, measurements and notes in page order.

    :param soup: Parsed record.
    :return: The rows of the table body.
    """
    table = soup.select_one("table#skinfold-table")
    assert table is not None
    return table.select("tbody > tr")


def test_tab_lists_the_note_of_every_measurement_that_has_one(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check the notes of the Bioimpedância tab: one detail row under each measurement with a note, newest first.

    The table keeps its 11 columns, and the note row spans them all.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 3, 1), OLD_NOTE)
    add_measurement(app, patient_id, date(2026, 3, 15), None)
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    soup = _record(app, client_admin, patient_id)

    table = soup.select_one("table#skinfold-table")
    assert table is not None and len(table.select("thead th")) == 11
    rows = _measurement_rows(soup)
    assert [row["class"][0] for row in rows] == [
        "skinfold-row",
        "skinfold-note-row",
        "skinfold-row",
        "skinfold-row",
        "skinfold-note-row",
    ]
    assert [
        bool(row.select_one("td[data-label='Data Medição']")) for row in rows if "skinfold-row" in row["class"]
    ] == [
        True,
        True,
        True,
    ]
    assert [row.select_one("td").get_text(strip=True) for row in rows if "skinfold-row" in row["class"]] == [
        "02/04/2026",
        "15/03/2026",
        "01/03/2026",
    ]
    note_rows = soup.select("tr.skinfold-note-row")
    assert [row.select_one(".skinfold-note-text").get_text() for row in note_rows] == [NEW_NOTE, OLD_NOTE]
    assert all(len(row.select("td")) == 1 and row.select_one("td")["colspan"] == "11" for row in note_rows)
    assert [row["class"] for row in rows if "has-note" in row["class"]] == [
        ["skinfold-row", "has-note"],
        ["skinfold-row", "has-note"],
    ]
    assert all(
        "Observações" in row.select_one(".skinfold-note-label").get_text()
        and "da medição de" in row.select_one(".skinfold-note-label .visually-hidden").get_text()
        for row in note_rows
    )
    assert all(row.select_one("button, a, input") is None for row in note_rows)


def test_tab_has_no_note_row_for_a_measurement_without_a_note(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check that the table has exactly the rows it had before when no measurement has a note.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 3, 1), None)

    soup = _record(app, client_admin, patient_id)

    assert soup.select(".skinfold-note-row, .has-note, .skinfold-note") == []
    assert len(_measurement_rows(soup)) == 1


def test_show_more_hides_and_shows_a_measurement_with_its_note(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check that the note row of a measurement after the fifth carries the same class that the toggle hides.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    for day in range(1, 8):
        add_measurement(app, patient_id, date(2026, 4, day), f"Nota do dia {day}" if day % 2 else None)

    soup = _record(app, client_admin, patient_id)

    rows = _measurement_rows(soup)
    pairs = []
    for index, row in enumerate(rows):
        if "skinfold-row" in row["class"]:
            following = rows[index + 1] if index + 1 < len(rows) else None
            has_note_row = following is not None and "skinfold-note-row" in following["class"]
            assert has_note_row is ("has-note" in row["class"])
            pairs.append((row, following if has_note_row else None))
    assert len(pairs) == 7
    for position, (row, note_row) in enumerate(pairs, start=1):
        extra = position > 5
        assert ("record-row-extra" in row["class"]) is extra
        if note_row is not None:
            assert ("record-row-extra" in note_row["class"]) is extra
    toggle = soup.select_one("#toggleSkinfold")
    assert toggle is not None and toggle["data-table"] == "skinfold-table"
    css = STATIC_CSS.read_text(encoding="utf-8")
    assert ".record-table:not(.is-expanded) .record-row-extra {\n    display: none;" in css


def test_custom_history_never_shows_a_note(app: Flask, client_admin: FlaskClient, patient_id: int) -> None:
    """Check that the history printed for the patient has neither the note nor the dialog.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    with app.app_context():
        db.session.add(AnthropometricEvaluation(patient_id=patient_id, **FIXED_EVALUATION))
        db.session.commit()
    add_measurement(app, patient_id, date(2026, 3, 1), OLD_NOTE)
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)
    with app.test_request_context():
        url = url_for("patients.view_custom_history", id=patient_id, pat_name="Paciente Observacoes")

    response = client_admin.get(url)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Retorno em 15 dias." not in html and OLD_NOTE not in html
    assert NOTE_MODAL_ID not in html and "Observações" not in html and "skinfold-note" not in html


def test_note_dialog_script_is_the_only_thing_that_opens_the_dialog(
    app: Flask, client_admin: FlaskClient, patient_id: int
) -> None:
    """Check that the dialog has no trigger in the markup, so only the record script opens it on load.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    """
    add_measurement(app, patient_id, date(2026, 4, 2), NEW_NOTE)

    soup = _record(app, client_admin, patient_id)

    assert soup.select(f"[data-bs-target='#{NOTE_MODAL_ID}'], [href='#{NOTE_MODAL_ID}']") == []
    assert "show" not in soup.select_one(f"#{NOTE_MODAL_ID}")["class"]
    assert soup.select_one("script[src$='js/patient_view.js']") is not None


@pytest.mark.parametrize("page", ["patients.add_skinfold", "patients.edit_skinfold"])
def test_measurement_forms_have_the_optional_observation_field(
    app: Flask, client_admin: FlaskClient, patient_id: int, page: str
) -> None:
    """Check the textarea of the forms: label, optional, 1000 characters limit, help text and the guard left alone.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param patient_id: Id of the patient.
    :param page: Endpoint of the form under test.
    """
    skinfold_id = add_measurement(app, patient_id, date(2026, 4, 2), "Nota guardada")
    values = (
        {"patient_id": patient_id}
        if page == "patients.add_skinfold"
        else {"patient_id": patient_id, "skinfold_id": skinfold_id}
    )
    with app.test_request_context():
        url = url_for(page, **values)

    soup = BeautifulSoup(client_admin.get(url).get_data(as_text=True), "html.parser")

    field = soup.select_one("form textarea#observacoes[name=observacoes]")
    assert field is not None
    assert field["maxlength"] == "1000" and not field.has_attr("required")
    label = soup.select_one("label[for=observacoes]")
    assert label is not None and label.get_text() == "Observações"
    help_text = soup.select_one("#observacoes-help")
    assert help_text is not None and field["aria-describedby"] == "observacoes-help"
    assert "mais recente" in help_text.get_text() and "ficha do paciente" in help_text.get_text()
    assert soup.select_one("#paError") is not None and soup.select_one("input#pa") is not None
    expected = "Nota guardada" if page == "patients.edit_skinfold" else ""
    assert field.get_text().removeprefix("\r\n") == expected
