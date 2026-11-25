"""E2E tests of the patient pages in Chrome: calculations, forms, list, record tabs, tables, charts and dialogs."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from flask import Flask

from app.models import AnthropometricEvaluation, Patients, SkinFolds, db
from tests.aliases import SeedData
from tests.e2e.test_responsive_layout import _login, _overflow, _settle, _snap, _url
from tests.form_helpers import changed_columns, row_values
from tests.patient_baselines import (
    ANTHRO_ADD_EXPECTED,
    ANTHRO_EDIT_EXPECTED,
    SKINFOLD_ADD_EXPECTED,
    SKINFOLD_EDIT_EXPECTED,
    SKINFOLD_PA_EXPECTED,
    SKINFOLD_WEIGHT_EXPECTED,
    STORED_NEW_PATIENT,
)
from tests.patient_cases import (
    ANTHRO_ADD_CASES,
    ANTHRO_COLUMNS,
    ANTHRO_EDIT_CASES,
    COMPLETE_PATIENT,
    FIXED_EVALUATION,
    NO_SPECIALIST_PATIENT,
    PATIENT_COLUMNS,
    SKINFOLD_ADD_CASES,
    SKINFOLD_COLUMNS,
    SKINFOLD_EDIT_CASES,
    SKINFOLD_PA_INPUTS,
    SKINFOLD_WEIGHT_INPUTS,
    AnthroAddCase,
    AnthroEditCase,
    SkinfoldAddCase,
    SkinfoldEditCase,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

ANTHRO_ADD_FIELDS = [
    "idade",
    "altura",
    "peso",
    "peso_anterior",
    "evolucao",
    "p_max",
    "p_ide",
    "p_min",
    "imc",
    "nutri_class",
    "necessidade_calorica",
    "ingestao_liquido",
]
ANTHRO_EDIT_FIELDS = [
    "data_avaliacao",
    "diet-select",
    "other_name",
    "idade",
    "evolucao",
    "p_max",
    "p_ide",
    "p_min",
    "imc",
    "nutri_class",
    "necessidade_calorica",
    "ingestao_liquido",
    "grau_atv_fisica",
]
SKINFOLD_EDIT_FIELDS = [
    "data_medicao",
    "altura",
    "peso",
    "massa_muscular",
    "gordura",
    "abdominal",
    "cintura",
    "quadril",
    "idade_metabolica",
    "pa",
]
INVALID_PRESSURE = "Formato inválido. Use até 3 dígitos antes da barra e até 2 dígitos depois (ex: 120/80)."
ADMIN_NAME = "Usuario Teste admin"


def _collect_errors(page: Page) -> list[str]:
    """Collect the uncaught JavaScript errors of a page.

    :param page: Playwright page.
    :return: The list that receives each error message as it happens.
    """
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


def _open_page(page: Page, live_server: str, path: str) -> None:
    """Open a page of the app and wait until it is loaded.

    :param page: Playwright page.
    :param live_server: Base URL of the running test server.
    :param path: URL path, with an optional hash.
    """
    page.goto(live_server + path)
    _settle(page)


def _values(page: Page, ids: list[str]) -> dict[str, str]:
    """Read the value of several controls by id.

    :param page: Playwright page.
    :param ids: Element ids.
    :return: The value of each control.
    """
    return {element_id: page.locator(f"#{element_id}").first.input_value() for element_id in ids}


def _stored(
    app: Flask, model: type[db.Model], filters: dict[str, Any], columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Read the stored rows of a model that match the filters, by id.

    :param app: Flask application.
    :param model: Model of the rows.
    :param filters: Column values the rows must have.
    :param columns: Columns to read.
    :return: One snapshot per row.
    """
    with app.app_context():
        rows = model.query.filter_by(**filters).order_by(model.id).all()
        return [row_values(row, columns) for row in rows]


def _row(app: Flask, model: type[db.Model], row_id: int, columns: tuple[str, ...]) -> dict[str, Any]:
    """Read the stored columns of a row.

    :param app: Flask application.
    :param model: Model of the row.
    :param row_id: Id of the row.
    :param columns: Columns to read.
    :return: The column values.
    """
    with app.app_context():
        return row_values(db.session.get(model, row_id), columns)


@pytest.mark.parametrize("case", ANTHRO_ADD_CASES, ids=lambda case: case.key)
def test_new_evaluation_page_computes_the_recorded_values(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int], case: AnthroAddCase
) -> None:
    """Check every computed field of the new evaluation page and what is stored, against the recorded values.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    :param case: Input set under test.
    """
    skinfolds = [row for row in (case.previous, case.last) if row]
    patient_id = case_patients(f"Caso {case.key}", case.gender, case.birth_date, skinfolds)
    expected = ANTHRO_ADD_EXPECTED[case.key]
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.add_anthro", patient_id=patient_id))
    assert _values(page, ANTHRO_ADD_FIELDS) == expected["load"]
    page.fill("#data_avaliacao", case.evaluation_date)
    assert _values(page, ANTHRO_ADD_FIELDS) == expected["after_date"]
    page.select_option("#diet-select", case.diet)
    assert page.locator("#other_name").is_visible() is expected["other_visible"]
    if case.other_name:
        page.fill("#other_name", case.other_name)
    page.select_option("#grau_atv_fisica", "Moderado")
    page.click("form.add-anthro-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))

    stored = _stored(app, AnthropometricEvaluation, {"patient_id": patient_id}, ANTHRO_COLUMNS)
    assert stored == [expected["stored"]]
    assert errors == []


@pytest.mark.parametrize("case", ANTHRO_EDIT_CASES, ids=lambda case: case.key)
def test_evaluation_edit_page_keeps_the_recorded_values(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int], case: AnthroEditCase
) -> None:
    """Check the loaded values, the age recalculation and the saved changes of the evaluation edit page.

    The page computes nothing but the age, so the stored results stay as the form shows them.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case: Input set under test.
    """
    patient_id = complete_patient["patient"]
    with app.app_context():
        row = AnthropometricEvaluation(patient_id=patient_id, **case.stored)
        db.session.add(row)
        db.session.commit()
        evaluation_id = row.id
    expected = ANTHRO_EDIT_EXPECTED[case.key]
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.edit_anthro", patient_id=patient_id, evaluation_id=evaluation_id))
    assert _values(page, ANTHRO_EDIT_FIELDS) == expected["load"]
    assert page.locator("#current-diet").inner_text().strip() == expected["current_diet"]
    assert page.locator("#other_name").is_visible() is expected["other_visible_load"]
    if case.new_date:
        page.fill("#data_avaliacao", case.new_date)
        assert _values(page, ["idade"]) == expected["after_date"]
    if case.diet:
        page.select_option("#diet-select", case.diet)
        assert page.locator("#other_name").is_visible() is expected["other_visible_after"]
        if case.other_name:
            page.fill("#other_name", case.other_name)
    before = _row(app, AnthropometricEvaluation, evaluation_id, ANTHRO_COLUMNS)
    page.click("form.edit-anthro-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))

    after = _row(app, AnthropometricEvaluation, evaluation_id, ANTHRO_COLUMNS)
    assert changed_columns(before, after) == expected["diff"]
    assert errors == []


def test_blood_pressure_and_weight_inputs_are_normalized_as_before(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check every recorded blood pressure input (value and message) and weight input (comma and dot).

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Pressao")
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_skinfold", patient_id=patient_id))

    pressure = {}
    for text in SKINFOLD_PA_INPUTS:
        page.fill("#pa", text)
        page.locator("#pa").blur()
        pressure[text] = {"value": page.locator("#pa").input_value(), "error": page.locator("#paError").inner_text()}
        page.fill("#pa", "")
        page.locator("#paError").evaluate("element => { element.textContent = ''; }")
    weight = {}
    for text in SKINFOLD_WEIGHT_INPUTS:
        page.fill("#peso", text)
        weight[text] = page.locator("#peso").input_value()

    assert pressure == SKINFOLD_PA_EXPECTED
    assert weight == SKINFOLD_WEIGHT_EXPECTED
    assert errors == []


@pytest.mark.parametrize("case", SKINFOLD_ADD_CASES, ids=lambda case: case.key)
def test_new_measurement_page_keeps_the_recorded_behavior(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int], case: SkinfoldAddCase
) -> None:
    """Check the loaded height, the typed values, the blocked submit and the stored rows of the new measurement page.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    :param case: Input set under test.
    """
    previous = [] if case.previous_height is None else [(date(2026, 8, 1), 80.0, case.previous_height)]
    patient_id = case_patients(f"Caso sk_{case.key}", skinfolds=previous)
    expected = SKINFOLD_ADD_EXPECTED[case.key]
    errors = _collect_errors(page)
    dialogs: list[str] = []

    def accept(dialog: Any) -> None:
        """Record the message of a dialog and accept it.

        :param dialog: Playwright dialog.
        """
        dialogs.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept)
    _login(page, live_server, "admin")
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)

    _open_page(page, live_server, url)
    assert _values(page, ["altura", "peso", "pa", "massa_muscular", "idade_metabolica"]) == expected["load"]
    page.fill("#data_medicao", "2026-11-20")
    if case.previous_height is None:
        page.fill("#altura", case.height)
    page.fill("#peso", case.weight)
    page.fill("#pa", case.pa)
    page.locator("#pa").blur()
    assert _values(page, ["altura", "peso", "pa"]) == expected["typed"]
    assert page.locator("#paError").inner_text() == expected["pa_error"]
    page.click("form.add-skinfold-form button[type=submit]")
    page.wait_for_timeout(800)

    assert dialogs == expected["dialogs"]
    assert page.url.endswith(url) is expected["stayed_on_page"]
    assert _stored(app, SkinFolds, {"patient_id": patient_id}, SKINFOLD_COLUMNS) == expected["stored"]
    assert errors == []


@pytest.mark.parametrize("case", SKINFOLD_EDIT_CASES, ids=lambda case: case.key)
def test_measurement_edit_page_keeps_the_recorded_behavior(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int], case: SkinfoldEditCase
) -> None:
    """Check the loaded values, the typed values and the saved changes of the measurement edit page.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case: Input set under test.
    """
    patient_id = complete_patient["patient"]
    with app.app_context():
        row = SkinFolds(patient_id=patient_id, **case.stored)
        db.session.add(row)
        db.session.commit()
        skinfold_id = row.id
    expected = SKINFOLD_EDIT_EXPECTED[case.key]
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.edit_skinfold", patient_id=patient_id, skinfold_id=skinfold_id))
    assert _values(page, SKINFOLD_EDIT_FIELDS) == expected["load"]
    if case.weight is not None:
        page.fill("#peso", case.weight)
    if case.pa is not None:
        page.fill("#pa", case.pa)
        page.locator("#pa").blur()
    assert _values(page, ["peso", "pa"]) == expected["typed"]
    assert page.locator("#paError").inner_text() == expected["pa_error"]
    before = _row(app, SkinFolds, skinfold_id, SKINFOLD_COLUMNS)
    page.click("form.edit-skinfold-form button[type=submit]")
    page.wait_for_url(re.compile(rf".*/patients/view/{patient_id}(#.*)?$"))

    assert changed_columns(before, _row(app, SkinFolds, skinfold_id, SKINFOLD_COLUMNS)) == expected["diff"]
    assert errors == []


def _patient_paths(app: Flask, seed: SeedData, complete: dict[str, int]) -> dict[str, str]:
    """List one path of every page of the patient area, with the tabs of the record.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param complete: Ids of the complete patient fixture.
    :return: The URL path of each page, keyed by a short name.
    """
    patient = int(seed["patient_nutritionist"])
    record = _url(app, "patients.view_patient", id=patient)
    return {
        "list": _url(app, "patients.list_patients"),
        "list-search": _url(app, "patients.list_patients", search="Zzz"),
        "add-patient": _url(app, "patients.add_patient"),
        "edit-patient": _url(app, "patients.edit_patient", id=patient),
        "record-dados": record,
        "record-avaliacoes": record + "#avaliacoes",
        "record-bioimpedancia": record + "#bioimpedancia",
        "record-evolucao": record + "#evolucao",
        "history": _url(app, "patients.view_custom_history", id=patient, pat_name="Paciente Teste 1"),
        "delete-patient": _url(app, "patients.delete_patient", id=patient),
        "add-anthro": _url(app, "patients.add_anthro", patient_id=patient),
        "edit-anthro": _url(
            app, "patients.edit_anthro", patient_id=complete["patient"], evaluation_id=complete["evaluation"]
        ),
        "add-skinfold": _url(app, "patients.add_skinfold", patient_id=patient),
        "edit-skinfold": _url(
            app, "patients.edit_skinfold", patient_id=complete["patient"], skinfold_id=complete["skinfold"]
        ),
    }


def test_no_page_errors_and_no_sideways_scroll_on_any_patient_page(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page], complete_patient: dict[str, int]
) -> None:
    """Open every patient page on both viewports: no script error and no horizontal scroll.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    device_name, page = device
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    for name, path in _patient_paths(app, seed, complete_patient).items():
        response = page.goto(live_server + path)
        _settle(page)
        page.wait_for_timeout(300)
        assert response is None or response.status == 200, name
        metrics = _overflow(page)
        assert metrics["scroll"] <= metrics["inner"], (device_name, name, metrics)
        _snap(page, device_name, f"patients-{name}")

    assert errors == []


def test_list_on_a_phone_has_no_sideways_scroll_and_the_menu_opens(
    app: Flask, live_server: str, mobile_page: Page
) -> None:
    """Check the list on a 390px phone: no horizontal scroll, cards and the actions menu that opens and closes.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    """
    from playwright.sync_api import expect

    _login(mobile_page, live_server, "admin")
    _open_page(mobile_page, live_server, _url(app, "patients.list_patients"))

    metrics = _overflow(mobile_page)
    assert metrics["inner"] == 390 and metrics["scroll"] <= metrics["inner"]
    first = mobile_page.locator("#patients-list > ul > li:visible").first
    assert first.evaluate("element => getComputedStyle(element).borderTopWidth") == "1px"
    toggle = first.locator(".patient-menu-toggle")
    menu = first.locator(".dropdown-menu")
    expect(menu).to_be_hidden()
    toggle.click()
    expect(menu).to_be_visible()
    expect(menu.get_by_role("link")).to_have_text(
        ["Ver ficha", "Editar", "Nova avaliação", "Nova bioimpedância", "Remover"]
    )
    _snap(mobile_page, "mobile", "patients-list-menu-open")
    mobile_page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    box = toggle.bounding_box()
    assert box is not None and box["height"] >= 44 and box["width"] >= 44


def test_list_targets_on_a_phone_are_at_least_44px(
    app: Flask, live_server: str, mobile_page: Page, case_patients: Callable[..., int]
) -> None:
    """Measure every tap target of the list on a 390px touch phone: name link, actions, pagination and quick forms.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param mobile_page: Playwright page of the phone context.
    :param case_patients: Factory of temporary patients.
    """
    for number in range(12):
        case_patients(f"Paciente Toque {number:02d}")
    _login(mobile_page, live_server, "admin")
    _open_page(mobile_page, live_server, _url(app, "patients.list_patients"))

    first = mobile_page.locator("#patients-list > ul > li:visible").first
    targets = {
        "patient name": first.locator(".patient-name"),
        "patient actions": first.locator(".patient-actions a:visible, .patient-actions button:visible"),
        "page buttons": mobile_page.locator("#pagination-buttons button"),
        "anthro select": mobile_page.locator("#anthro-form .select2-selection"),
        "skinfold select": mobile_page.locator("#skinfold-form .select2-selection"),
        "quick form buttons": mobile_page.locator(".quick-form-row .btn"),
    }
    small: dict[str, list[tuple[float, float]]] = {}
    for name, locator in targets.items():
        assert locator.count() > 0, name
        for index in range(locator.count()):
            box = locator.nth(index).bounding_box()
            assert box is not None, name
            if box["height"] < 43.5 or box["width"] < 43.5:
                small.setdefault(name, []).append((box["width"], box["height"]))
    assert small == {}


def test_nutritionist_menu_has_no_remove_entry(app: Flask, live_server: str, page: Page) -> None:
    """Check the actions menu of a nutritionist: the four actions and no removal.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    _login(page, live_server, "nutritionist")
    _open_page(page, live_server, _url(app, "patients.list_patients"))

    first = page.locator("#patients-list > ul > li:visible").first
    first.locator(".patient-menu-toggle").click()
    expect(first.locator(".dropdown-menu").get_by_role("link")).to_have_text(
        ["Ver ficha", "Editar", "Nova avaliação", "Nova bioimpedância"]
    )
    expect(page.get_by_text("Remover")).to_have_count(0)


def test_pagination_with_more_patients_than_one_page(
    app: Flask, live_server: str, device: tuple[str, Page], case_patients: Callable[..., int]
) -> None:
    """Check the pagination with more patients than one page, creating temporary patients for it.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    device_name, page = device
    for number in range(32):
        case_patients(f"Paciente Paginacao {number:02d}")
    with app.app_context():
        total = Patients.query.count()
    pages = -(-total // 10)
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.list_patients"))

    items = page.locator("#patients-list > ul > li")
    info = page.locator("#pagination-info")
    assert pages >= 4 and items.count() == total
    expect(page.locator("#patients-list > ul > li:visible")).to_have_count(10)
    expect(info).to_have_text(f"Página 1 de {pages} - Total de pacientes: {total}")
    buttons = page.locator("#pagination-buttons button")
    expect(buttons).to_have_text(["1", "2", "3", "Próxima", "Última"])
    expect(buttons.first).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="2", exact=True).click()
    expect(info).to_have_text(f"Página 2 de {pages} - Total de pacientes: {total}")
    expect(page.locator("#patients-list > ul > li:visible")).to_have_count(10)
    page.get_by_role("button", name="Próxima").click()
    expect(info).to_have_text(f"Página 4 de {pages} - Total de pacientes: {total}")
    expect(page.locator("#pagination-buttons button").first).to_have_text("Anterior")
    expect(page.locator("#patients-list > ul > li:visible")).to_have_count(min(10, total - 30))
    page.get_by_role("button", name="Anterior").click()
    expect(info).to_have_text(f"Página 3 de {pages} - Total de pacientes: {total}")
    page.get_by_role("button", name="Última").click()
    expect(info).to_have_text(f"Página {pages} de {pages} - Total de pacientes: {total}")
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    _snap(page, device_name, "patients-list-paginated")
    assert errors == []


def test_search_without_results_in_the_browser(app: Flask, live_server: str, page: Page) -> None:
    """Check the search typed in the page: the empty state shows the text and the link clears the search.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.list_patients"))
    page.fill("#patient-search", "Ninguém Assim")
    page.get_by_role("button", name="Pesquisar").click()

    expect(page.locator(".empty-state")).to_contain_text("Ninguém Assim")
    expect(page.locator(".patient-item")).to_have_count(0)
    page.get_by_role("link", name="Limpar busca").click()
    page.wait_for_url(re.compile(r".*/patients-manager/patients$"))
    expect(page.locator("#patients-list > ul > li:visible").first).to_be_visible()


def test_quick_forms_open_the_page_of_the_chosen_patient(
    app: Flask, seed: SeedData, live_server: str, page: Page
) -> None:
    """Check the shortcuts of the list: a message without a patient and the redirect with one chosen in select2.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.list_patients"))
    page.get_by_role("button", name="Realizar avaliação").click()
    expect(page.locator("#anthro-form .quick-form-error")).to_have_text("Selecione um paciente.")

    page.locator("#anthro-form .select2-container").click()
    page.locator(".select2-results__option", has_text="Paciente Teste 1").click()
    page.get_by_role("button", name="Realizar avaliação").click()
    page.wait_for_url(re.compile(rf".*/patients/{seed['patient_nutritionist']}/anthropometric/add$"))

    _open_page(page, live_server, _url(app, "patients.list_patients"))
    page.locator("#skinfold-form .select2-container").click()
    page.locator(".select2-results__option", has_text="Paciente Teste 1").click()
    page.get_by_role("button", name="Aferir bioimpedância").click()
    page.wait_for_url(re.compile(rf".*/patients/{seed['patient_nutritionist']}/skinfolds/add$"))


def _fill_new_patient_identity(page: Page, seed: SeedData, stored: dict[str, Any], yes: bool) -> None:
    """Fill the personal data, contact and the three yes/no answers of the new patient form.

    :param page: Playwright page on the new patient form.
    :param seed: Ids of the fake records.
    :param stored: Recorded patient that the form must create.
    :param yes: Whether the variant with the conditional answers is being filled.
    """
    page.fill("#name", stored["name"])
    page.select_option("#gender", stored["gender"])
    page.fill("#birth_date", stored["birth_date"])
    page.fill("#cpf", "98765432100" if yes else "12345678909")
    page.fill("#phone", "31987654321" if yes else "3133334444")
    page.fill("#email", stored["email"])
    page.select_option("#specialist", str(seed["specialist_other"]))
    page.select_option("#medication", stored["medication"])
    page.select_option("#allergies", stored["allergies"])
    page.select_option("#physical_activities", stored["physical_activities"])


def _fill_new_patient_habits(page: Page, stored: dict[str, Any]) -> None:
    """Fill the habits and the objective of the new patient form.

    :param page: Playwright page on the new patient form.
    :param stored: Recorded patient that the form must create.
    """
    page.fill("#intestine", str(stored["intestine"]))
    page.fill("#water", str(stored["water"]))
    page.select_option("#heartburn", stored["heartburn"])
    page.fill("#objective", stored["objective"])
    page.locator("#objective").blur()


@pytest.mark.parametrize("variant", ["sim", "nao"])
def test_new_patient_form_in_the_browser_creates_the_recorded_patient(
    app: Flask, seed: SeedData, live_server: str, page: Page, variant: str
) -> None:
    """Fill the new patient form like a user, with and without the conditional answers, and compare what is stored.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param variant: Which recorded patient to create.
    """
    from playwright.sync_api import expect

    stored = STORED_NEW_PATIENT[variant]
    yes = variant == "sim"
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_patient"))
    for field in ("#medications_details", "#allergies_details", "#physical_details", "#hours", "#frequency"):
        expect(page.locator(field)).to_be_hidden()

    _fill_new_patient_identity(page, seed, stored, yes)
    for field in ("#medications_details", "#allergies_details", "#physical_details", "#hours"):
        if yes:
            expect(page.locator(field)).to_be_visible()
        else:
            expect(page.locator(field)).to_be_hidden()
    if yes:
        expect(page.locator("#medications_details")).to_have_attribute("required", "")
        page.fill("#medications_details", stored["medications_details"])
        page.fill("#allergies_details", stored["allergies_details"])
        page.fill("#physical_details", stored["physical_details"])
        page.fill("#hours", stored["hours"][:5])
        page.fill("#frequency", str(stored["frequency"]))
    _fill_new_patient_habits(page, stored)
    assert page.locator("#cpf").input_value() == stored["cpf"]
    assert page.locator("#phone").input_value() == stored["tel_number"]
    _snap(page, "desktop", f"patients-add-filled-{variant}")
    try:
        page.get_by_role("button", name="Cadastrar paciente").click()
        page.wait_for_url(re.compile(r".*/patients-manager/patients$"))

        with app.app_context():
            snapshot = row_values(Patients.query.filter_by(name=stored["name"]).one(), PATIENT_COLUMNS)
        assert snapshot.pop("specialist_id") == int(seed["specialist_other"])
        assert snapshot == stored
        assert errors == []
    finally:
        with app.app_context():
            Patients.query.filter_by(name=stored["name"]).delete(synchronize_session=False)
            db.session.commit()


def test_new_patient_form_keeps_the_physical_details_after_answering_no(
    app: Flask, seed: SeedData, live_server: str, page: Page
) -> None:
    """Type the physical activity details, switch the answer back to "não" and check that they are still stored.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    stored = STORED_NEW_PATIENT["nao"]
    typed = "Bike"
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_patient"))
    _fill_new_patient_identity(page, seed, {**stored, "physical_activities": "sim"}, False)
    expect(page.locator("#physical_details")).to_be_visible()
    page.fill("#physical_details", typed)
    page.select_option("#physical_activities", "não")
    expect(page.locator("#physical_details")).to_be_hidden()
    assert page.locator("#physical_details").input_value() == typed
    _fill_new_patient_habits(page, stored)
    try:
        page.get_by_role("button", name="Cadastrar paciente").click()
        page.wait_for_url(re.compile(r".*/patients-manager/patients$"))

        with app.app_context():
            snapshot = row_values(Patients.query.filter_by(name=stored["name"]).one(), PATIENT_COLUMNS)
        assert snapshot["physical_activities"] == "não"
        assert snapshot["physical_details"] == typed
        assert errors == []
    finally:
        with app.app_context():
            Patients.query.filter_by(name=stored["name"]).delete(synchronize_session=False)
            db.session.commit()


def test_new_patient_form_validates_the_formats_in_the_browser(app: Flask, live_server: str, page: Page) -> None:
    """Check the messages of the CPF, phone and e-mail validation of the new patient form.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.add_patient"))

    messages = {}
    for field, text in (("#cpf", "123"), ("#cpf", "abc"), ("#phone", "123"), ("#email", "sem-arroba")):
        page.fill(field, text)
        page.locator(field).blur()
        messages[(field, text)] = page.locator(field).evaluate("element => element.validationMessage")
        page.fill(field, "")
        page.locator(field).evaluate("element => element.setCustomValidity('')")

    assert messages[("#cpf", "123")] == "CPF inválido. Precisa conter 11 dígitos."
    assert messages[("#cpf", "abc")] == "CPF inválido. Não pode conter letras."
    assert messages[("#phone", "123")] == "Telefone inválido. Precisa conter 10 ou 11 dígitos."
    assert messages[("#email", "sem-arroba")] == "Email inválido."


def test_edit_page_saves_only_the_changed_field_in_the_browser(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int]
) -> None:
    """Change one field of the edit page and save it: only that column changes and the user lands on the list.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient_id = complete_patient["patient"]
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.edit_patient", id=patient_id))
    before = _row(app, Patients, patient_id, PATIENT_COLUMNS)

    page.fill("#objective", "Objetivo alterado no navegador")
    page.get_by_role("button", name="Salvar alterações").click()
    page.wait_for_url(re.compile(r".*/patients-manager/patients$"))

    diff = changed_columns(before, _row(app, Patients, patient_id, PATIENT_COLUMNS))
    assert diff == {"objective": [COMPLETE_PATIENT["objective"], "Objetivo alterado no navegador"]}
    assert errors == []


def test_edit_page_saves_a_patient_without_e_mail_or_cpf(
    app: Flask, live_server: str, page: Page, case_patients: Callable[..., int]
) -> None:
    """Check that a patient with no e-mail and no CPF can be edited: the optional fields do not block the save.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients(**NO_SPECIALIST_PATIENT, specialist="specialist_other")
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.edit_patient", id=patient_id))

    page.fill("#objective", "Objetivo sem e-mail")
    page.get_by_role("button", name="Salvar alterações").click()
    page.wait_for_url(re.compile(r".*/patients-manager/patients$"))

    assert _row(app, Patients, patient_id, ("objective", "email", "cpf")) == {
        "objective": "Objetivo sem e-mail",
        "email": "",
        "cpf": "",
    }


def test_edit_page_shows_the_conditional_fields_only_when_they_apply(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int], case_patients: Callable[..., int]
) -> None:
    """Check the dependent fields of the edit page: shown for answers "sim" or filled data, hidden otherwise.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    plain = case_patients("Paciente Sem Detalhes")
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.edit_patient", id=complete_patient["patient"]))
    for field in ("#medications_details", "#allergies_details", "#physical_details", "#hours", "#frequency"):
        expect(page.locator(field)).to_be_visible()
    _open_page(page, live_server, _url(app, "patients.edit_patient", id=plain))
    for field in ("#medications_details", "#allergies_details", "#physical_details", "#hours", "#frequency"):
        expect(page.locator(field)).to_be_hidden()
    page.select_option("#medication", "sim")
    expect(page.locator("#medications_details")).to_be_visible()
    page.select_option("#medication", "não")
    expect(page.locator("#medications_details")).to_be_hidden()


def _extra_evaluations(app: Flask, patient_id: int, count: int) -> None:
    """Add evaluations to a patient, all older than the fixed one.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :param count: How many evaluations to add.
    """
    with app.app_context():
        for number in range(count):
            values = {**FIXED_EVALUATION, "data_avaliacao": date(2026, 4, 1) - timedelta(days=number)}
            db.session.add(AnthropometricEvaluation(patient_id=patient_id, **values))
        db.session.commit()


def _extra_measurements(app: Flask, patient_id: int, weights: list[float]) -> None:
    """Add measurements to a patient, one per day from the first of June 2026.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :param weights: Weight of each measurement, in order.
    """
    with app.app_context():
        for number, weight in enumerate(weights):
            db.session.add(
                SkinFolds(
                    patient_id=patient_id,
                    data_medicao=date(2026, 6, 1) + timedelta(days=number),
                    altura=1.7,
                    peso=weight,
                    massa_muscular=0,
                    gordura=0,
                    abdominal=0,
                    cintura=0,
                    quadril=0,
                    idade_metabolica=0,
                    pa="12/8",
                )
            )
        db.session.commit()


def test_record_tabs_switch_and_keep_the_hash(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int]
) -> None:
    """Check the tabs of the record: clicking switches the panel and sets the hash, which survives a reload.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    errors = _collect_errors(page)
    record = _url(app, "patients.view_patient", id=complete_patient["patient"])
    _login(page, live_server, "admin")
    _open_page(page, live_server, record)
    expect(page.locator("#pane-dados")).to_be_visible()
    expect(page.locator("#pane-avaliacoes")).to_be_hidden()

    for key, title in (("avaliacoes", "Avaliações"), ("bioimpedancia", "Bioimpedância"), ("evolucao", "Evolução")):
        page.get_by_role("tab", name=re.compile(title)).click()
        expect(page.locator(f"#pane-{key}")).to_be_visible()
        expect(page.locator(f"#tab-{key}")).to_have_attribute("aria-selected", "true")
        assert page.url.endswith(f"#{key}")
        assert page.locator(".tab-pane:visible").count() == 1
    page.reload()
    _settle(page)
    expect(page.locator("#pane-evolucao")).to_be_visible()
    expect(page.locator("#tab-evolucao")).to_have_attribute("aria-selected", "true")

    _open_page(page, live_server, record + "#bioimpedancia")
    expect(page.locator("#pane-bioimpedancia")).to_be_visible()
    page.get_by_role("tab", name="Dados").click()
    expect(page.locator("#pane-dados")).to_be_visible()
    page.keyboard.press("Tab")
    assert errors == []


def test_back_from_the_edit_pages_and_saving_return_to_the_tab(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int]
) -> None:
    """Check that cancelling or saving an evaluation or a measurement brings the user back to its tab of the record.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    patient_id = complete_patient["patient"]
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.view_patient", id=patient_id) + "#avaliacoes")
    page.get_by_role("link", name=re.compile("Editar avaliação de")).click()
    page.get_by_role("link", name="Cancelar").click()
    page.wait_for_url(re.compile(r".*/patients/view/\d+#avaliacoes$"))
    expect(page.locator("#pane-avaliacoes")).to_be_visible()

    _open_page(page, live_server, _url(app, "patients.view_patient", id=patient_id))
    page.get_by_role("tab", name=re.compile("Bioimpedância")).click()
    page.get_by_role("link", name=re.compile("Editar medição de")).click()
    page.get_by_role("button", name="Salvar bioimpedância").click()
    page.wait_for_url(re.compile(r".*/patients/view/\d+#bioimpedancia$"))
    expect(page.locator("#pane-bioimpedancia")).to_be_visible()

    _open_page(
        page,
        live_server,
        _url(app, "patients.edit_anthro", patient_id=patient_id, evaluation_id=complete_patient["evaluation"]),
    )
    page.get_by_role("button", name="Atualizar avaliação").click()
    page.wait_for_url(re.compile(r".*/patients/view/\d+#avaliacoes$"))
    expect(page.locator("#pane-avaliacoes")).to_be_visible()


def test_record_tables_are_tables_on_desktop_and_cards_on_a_phone(
    app: Flask, live_server: str, device: tuple[str, Page], complete_patient: dict[str, int]
) -> None:
    """Check the evaluation table: scrolling inside its card on desktop, cards without sideways scroll on a phone.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    device_name, page = device
    _extra_evaluations(app, complete_patient["patient"], 6)
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.view_patient", id=complete_patient["patient"]) + "#avaliacoes")
    expect(page.locator("#pane-avaliacoes")).to_be_visible()

    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    row_display = page.locator("#anthro-table tbody tr").first.evaluate("element => getComputedStyle(element).display")
    header_box = page.locator("#anthro-table thead").first.bounding_box()
    wrapper = page.locator(".table-responsive").first
    if device_name == "mobile":
        assert row_display == "block" and header_box is not None and header_box["width"] <= 1
        assert wrapper.evaluate("element => element.scrollWidth <= element.clientWidth")
        label = (
            page.locator("#anthro-table tbody tr")
            .first.locator("td")
            .first.evaluate("element => getComputedStyle(element, '::before').content")
        )
        assert "Data Avalia" in label
    else:
        assert row_display == "table-row" and header_box is not None and header_box["width"] > 100
        assert wrapper.evaluate("element => getComputedStyle(element).overflowX") == "auto"
    rows = page.locator("#anthro-table tbody tr")
    assert rows.count() == 7
    expect(page.locator("#anthro-table tbody tr:visible")).to_have_count(5)
    toggle = page.locator("#toggleAnthro")
    toggle.click()
    expect(page.locator("#anthro-table tbody tr:visible")).to_have_count(7)
    expect(toggle).to_have_text("Mostrar menos avaliações")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    assert page.locator("#anthro-table").get_attribute("class").count("is-expanded") == 1
    assert all(style is None for style in [rows.nth(index).get_attribute("style") for index in range(7)])
    toggle.click()
    expect(page.locator("#anthro-table tbody tr:visible")).to_have_count(5)
    _snap(page, device_name, "patients-record-tables")


def test_weight_chart_renders_with_measurements_and_an_empty_state_without(
    app: Flask,
    live_server: str,
    device: tuple[str, Page],
    complete_patient: dict[str, int],
    case_patients: Callable[..., int],
) -> None:
    """Check the evolution chart: drawn from the measurements of the page, sized to the viewport, and the empty state.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case_patients: Factory of temporary patients.
    """
    from playwright.sync_api import expect

    device_name, page = device
    _extra_measurements(app, complete_patient["patient"], [72.5, 71.0, 70.2])
    empty_patient = case_patients("Paciente Sem Grafico")
    errors = _collect_errors(page)
    _login(page, live_server, "admin")

    _open_page(page, live_server, _url(app, "patients.view_patient", id=complete_patient["patient"]) + "#evolucao")
    canvas = page.locator("canvas#weightChart")
    expect(canvas).to_be_visible()
    page.wait_for_function("() => window.Chart && window.Chart.getChart(document.getElementById('weightChart'))")
    chart = page.evaluate(
        """() => {
            const instance = window.Chart.getChart(document.getElementById('weightChart'));
            return {
                labels: instance.data.labels,
                weights: instance.data.datasets[0].data,
                width: instance.width,
                height: instance.height,
                version: window.Chart.version,
            };
        }"""
    )
    assert chart["weights"] == [70.0, 72.5, 71.0, 70.2]
    assert chart["labels"] == ["10/05/2026", "01/06/2026", "02/06/2026", "03/06/2026"]
    assert chart["version"] == "4.4.1"
    box = canvas.bounding_box()
    assert box is not None and box["width"] > 200 and box["height"] > 150
    assert box["x"] + box["width"] <= page.viewport_size["width"] + 1
    assert chart["width"] > 200 and chart["height"] > 150
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    _snap(page, device_name, "patients-record-chart")

    _open_page(page, live_server, _url(app, "patients.view_patient", id=empty_patient) + "#evolucao")
    expect(page.locator("#pane-evolucao .empty-state")).to_be_visible()
    expect(page.locator("canvas")).to_have_count(0)
    assert errors == []


def test_custom_history_chart_renders_and_prints(
    app: Flask, seed: SeedData, live_server: str, device: tuple[str, Page]
) -> None:
    """Check the custom history: pinned Chart.js 4.4.1 draws the weights and the print button opens the print dialog.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param device: Viewport name and Playwright page.
    """
    from playwright.sync_api import expect

    device_name, page = device
    errors = _collect_errors(page)
    _login(page, live_server, "admin")
    _open_page(
        page,
        live_server,
        _url(app, "patients.view_custom_history", id=int(seed["patient_nutritionist"]), pat_name="Paciente Teste 1"),
    )

    page.wait_for_function("() => window.Chart && window.Chart.getChart(document.getElementById('evolutionsChart'))")
    assert page.evaluate("() => window.Chart.version") == "4.4.1"
    assert page.locator("canvas#evolutionsChart").bounding_box()["width"] > 200
    metrics = _overflow(page)
    assert metrics["scroll"] <= metrics["inner"], (device_name, metrics)
    page.evaluate("() => { window.printed = 0; window.print = () => { window.printed += 1; }; }")
    page.get_by_role("button", name="Imprimir histórico").click()
    assert page.evaluate("() => window.printed") == 1
    expect(page.get_by_role("heading", name="Histórico personalizado", level=1)).to_be_visible()
    assert errors == []


def test_deleting_from_the_record_asks_for_confirmation(
    app: Flask, live_server: str, page: Page, complete_patient: dict[str, int]
) -> None:
    """Check the delete buttons: dismissing the confirmation keeps the row, accepting removes it and stays on the tab.

    :param app: Flask application.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    from playwright.sync_api import expect

    messages: list[str] = []
    decisions = iter([False, True, True])

    def answer(dialog: Any) -> None:
        """Record the confirmation message and answer it with the next decision.

        :param dialog: Playwright dialog.
        """
        messages.append(dialog.message)
        if next(decisions):
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", answer)
    patient_id = complete_patient["patient"]
    _login(page, live_server, "admin")
    _open_page(page, live_server, _url(app, "patients.view_patient", id=patient_id) + "#avaliacoes")

    page.get_by_role("button", name=re.compile("Excluir avaliação de")).click()
    expect(page.locator("#anthro-table tbody tr")).to_have_count(1)
    page.get_by_role("button", name=re.compile("Excluir avaliação de")).click()
    page.wait_for_url(re.compile(r".*/patients/view/\d+#avaliacoes$"))
    expect(page.locator("#toast-region")).to_contain_text("Avaliação antropométrica removida com sucesso!")
    expect(page.locator("#pane-avaliacoes")).to_be_visible()
    expect(page.locator("#pane-avaliacoes .empty-state")).to_be_visible()
    page.get_by_role("tab", name=re.compile("Bioimpedância")).click()
    page.get_by_role("button", name=re.compile("Excluir medição de")).click()
    expect(page.locator("#toast-region")).to_contain_text("Medição de bioimpedância removida com sucesso!")

    assert messages == [
        "Tem certeza que deseja remover esta avaliação?",
        "Tem certeza que deseja remover esta avaliação?",
        "Tem certeza que deseja remover essa medição? (Revise a Antropometria após a remoção)",
    ]
    with app.app_context():
        assert db.session.get(AnthropometricEvaluation, complete_patient["evaluation"]) is None
        assert SkinFolds.query.filter_by(patient_id=patient_id).count() == 0


def test_record_for_a_nutritionist_has_no_remove_button(
    app: Flask, seed: SeedData, live_server: str, page: Page
) -> None:
    """Check that a nutritionist sees the record of their patient without the removal button.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param live_server: Base URL of the running test server.
    :param page: Playwright page of the desktop context.
    """
    from playwright.sync_api import expect

    _login(page, live_server, "nutritionist")
    _open_page(page, live_server, _url(app, "patients.view_patient", id=int(seed["patient_nutritionist"])))

    expect(page.get_by_role("link", name="Editar", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Remover")).to_have_count(0)
    _snap(page, "desktop", "patients-record-nutritionist")
