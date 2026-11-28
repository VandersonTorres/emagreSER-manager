"""Form contract of the patient pages: names and values they submit, and what the views store from them."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from sqlalchemy import func

from app.models import AnthropometricEvaluation, Patients, SkinFolds, Specialists, db
from tests.aliases import SeedData
from tests.form_helpers import changed_columns, form_entries, form_names, row_values
from tests.patient_baselines import (
    ANTHRO_ADD_EXPECTED,
    ANTHRO_EDIT_EXPECTED,
    EDIT_PATIENT_DIFFS,
    FORM_FIELD_NAMES,
    FORM_VALUES,
    SKINFOLD_ADD_EXPECTED,
    SKINFOLD_EDIT_EXPECTED,
    STORED_NEW_PATIENT,
)
from tests.patient_cases import (
    ADDED_FIELD_RENDERED_VALUES,
    ADDED_FIELDS,
    ANTHRO_ADD_CASES,
    ANTHRO_COLUMNS,
    ANTHRO_EDIT_CASES,
    FIXED_SKINFOLD,
    NO_SPECIALIST_PATIENT,
    PATIENT_COLUMNS,
    REMOVED_FIELD_STORED_VALUES,
    REMOVED_FIELDS,
    SECONDS_PATIENT,
    SKINFOLD_ADD_CASES,
    SKINFOLD_COLUMNS,
    SKINFOLD_EDIT_CASES,
    AnthroAddCase,
    AnthroEditCase,
    SkinfoldAddCase,
    SkinfoldEditCase,
)
from tests.test_csrf_rendering import csrf_on  # noqa: F401

SCRIPT_COMPUTED = {
    "add_anthro": {
        "idade",
        "evolucao",
        "p_max",
        "p_ide",
        "p_min",
        "imc",
        "nutri_class",
        "necessidade_calorica",
        "ingestao_liquido",
    },
    "edit_anthro": {"idade"},
}
ADMIN_NAME = "Usuario Teste admin"
CSRF_FIELD = "csrf_token"
GET_FORM_PAGES = frozenset({"search", "quick_anthro", "quick_skinfold"})


def _expected_names(page: str) -> list[str]:
    """Take the recorded field names of a page without the fields the clinic no longer asks and with the added ones.

    :param page: Name of the page in the baselines.
    :return: The sorted names the page must submit.
    """
    recorded = {name for name in FORM_FIELD_NAMES[page] if name not in REMOVED_FIELDS}
    return sorted(recorded | ADDED_FIELDS.get(page, frozenset()))


def _field_names(html: str, selector: str) -> list[str]:
    """List the names a form submits, sorted and without the CSRF token, which every POST form carries.

    :param html: HTML of the page.
    :param selector: CSS selector of the form.
    :return: The sorted names of the fields of the form.
    """
    return [name for name in form_names(html, selector) if name != CSRF_FIELD]


def _url(app: Flask, endpoint: str, **values: int | str) -> str:
    """Build a URL path outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


def _html(client: FlaskClient, url: str) -> str:
    """Open a page that must answer 200.

    :param client: Test client.
    :param url: URL path of the page.
    :return: The HTML of the page.
    """
    response = client.get(url)
    assert response.status_code == 200, f"GET {url}: {response.status_code}"
    return response.get_data(as_text=True)


def _post_values(client: FlaskClient, url: str, selector: str, overrides: dict[str, str]) -> dict[str, str]:
    """Build what a browser posts for a form: the rendered values with the user's changes on top.

    :param client: Test client.
    :param url: URL path of the page with the form.
    :param selector: CSS selector of the form.
    :param overrides: Values typed or computed by the page scripts, by field name.
    :return: The data to post.
    """
    data = dict(form_entries(_html(client, url), selector))
    data.update(overrides)
    return data


def _snapshot(app: Flask, model: type[db.Model], row_id: int, columns: tuple[str, ...]) -> dict[str, Any]:
    """Read the stored columns of a row.

    :param app: Flask application.
    :param model: Model of the row.
    :param row_id: Id of the row.
    :param columns: Columns to read.
    :return: The column values by name.
    """
    with app.app_context():
        return row_values(db.session.get(model, row_id), columns)


@pytest.fixture
def pages(app: Flask, seed: SeedData, complete_patient: dict[str, int]) -> dict[str, tuple[str, str]]:
    """Map each form page of the patient area to its URL and form selector.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :return: The (URL path, form selector) of each page, keyed by the name used in the baselines.
    """
    patient = int(seed["patient_nutritionist"])
    other = int(seed["patient_other"])
    complete = complete_patient["patient"]
    return {
        "add_patient": (_url(app, "patients.add_patient"), "form.add-patient-form"),
        "edit_patient": (_url(app, "patients.edit_patient", id=patient), "form.edit-patient-form"),
        "add_anthro": (_url(app, "patients.add_anthro", patient_id=patient), "form.add-anthro-form"),
        "edit_anthro": (
            _url(app, "patients.edit_anthro", patient_id=complete, evaluation_id=complete_patient["evaluation"]),
            "form.edit-anthro-form",
        ),
        "add_skinfold": (_url(app, "patients.add_skinfold", patient_id=patient), "form.add-skinfold-form"),
        "edit_skinfold": (
            _url(app, "patients.edit_skinfold", patient_id=complete, skinfold_id=complete_patient["skinfold"]),
            "form.edit-skinfold-form",
        ),
        "delete_patient": (_url(app, "patients.delete_patient", id=other), ".confirm-card form"),
        "search": (_url(app, "patients.list_patients"), "form.patient-search"),
        "quick_anthro": (_url(app, "patients.list_patients"), "#anthro-form"),
        "quick_skinfold": (_url(app, "patients.list_patients"), "#skinfold-form"),
        "delete_evaluation": (_url(app, "patients.view_patient", id=complete), "form[action*='/evaluation/delete/']"),
        "delete_skinfold": (_url(app, "patients.view_patient", id=complete), "form[action*='/skinfold/delete/']"),
    }


@pytest.mark.parametrize("page", sorted(FORM_FIELD_NAMES))
def test_form_submits_the_recorded_field_names(
    client_admin: FlaskClient, pages: dict[str, tuple[str, str]], page: str
) -> None:
    """Check that each form sends exactly the field names recorded before the redesign.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    :param page: Name of the page under test.
    """
    url, selector = pages[page]

    names = _field_names(_html(client_admin, url), selector)

    assert names == _expected_names(page), page


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize("page", sorted(FORM_FIELD_NAMES))
def test_every_post_form_carries_the_csrf_token(
    client_admin: FlaskClient, pages: dict[str, tuple[str, str]], page: str
) -> None:
    """Check that, with CSRF protection on, every form that posts carries the token and the GET forms do not.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    :param page: Name of the page under test.
    """
    url, selector = pages[page]

    names = form_names(_html(client_admin, url), selector)

    assert (CSRF_FIELD in names) is (page not in GET_FORM_PAGES), page
    assert [name for name in names if name != CSRF_FIELD] == _expected_names(page)


def test_only_the_measurement_forms_submit_the_observation(
    client_admin: FlaskClient, pages: dict[str, tuple[str, str]]
) -> None:
    """Check that the added field is submitted by the two measurement forms and by no other form of the area.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    """
    assert set(ADDED_FIELDS) <= set(FORM_FIELD_NAMES)
    assert ADDED_FIELDS == {"add_skinfold": {"observacoes"}, "edit_skinfold": {"observacoes"}}
    for page, (url, selector) in pages.items():
        names = _field_names(_html(client_admin, url), selector)

        assert ("observacoes" in names) is (page in ADDED_FIELDS), page
        assert all(name in FORM_FIELD_NAMES[page] for name in names if name not in ADDED_FIELDS.get(page, ())), page


def test_pages_are_listed_in_the_baseline(pages: dict[str, tuple[str, str]]) -> None:
    """Check that every form page of the area has a recorded baseline and the other way round.

    :param pages: URL and form selector of each page.
    """
    assert sorted(pages) == sorted(FORM_FIELD_NAMES)


def _expected_values(key: str, page: str, **replace: str) -> dict[str, str]:
    """Take the recorded values of a form without the fields a script computes in the browser or the clinic dropped.

    :param key: Key of the recorded values.
    :param page: Page name, used to look up the script computed fields.
    :param replace: Fields whose value depends on the seed, by name.
    :return: The values the page itself renders.
    """
    skipped = SCRIPT_COMPUTED.get(page, set()) | REMOVED_FIELDS
    values = {name: value for name, value in FORM_VALUES[key].items() if name not in skipped}
    values.update(replace)
    return values


def _rendered_values(
    client: FlaskClient, pages: dict[str, tuple[str, str]], page: str, page_key: str
) -> dict[str, str]:
    """Read the values a page renders for a form, without the fields a script computes in the browser.

    :param client: Test client.
    :param pages: URL and form selector of each page.
    :param page: Name of the page.
    :param page_key: Key of the page in the baseline, used to look up the script computed fields.
    :return: The rendered values by field name.
    """
    url, selector = pages[page]
    skipped = SCRIPT_COMPUTED.get(page_key, set()) | {CSRF_FIELD}
    return {name: value for name, value in form_entries(_html(client, url), selector) if name not in skipped}


def test_add_patient_form_starts_as_before(client_admin: FlaskClient, pages: dict[str, tuple[str, str]]) -> None:
    """Check the initial values of the new patient form: everything empty and the frequency at zero.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    """
    values = _rendered_values(client_admin, pages, "add_patient", "add_patient")

    assert values == _expected_values("add_patient_initial", "add_patient")


def test_edit_patient_form_keeps_the_values_of_a_record(
    client_admin: FlaskClient, pages: dict[str, tuple[str, str]], seed: SeedData
) -> None:
    """Check that the edit form of the seeded patient renders the same values as before.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    :param seed: Ids of the fake records.
    """
    values = _rendered_values(client_admin, pages, "edit_patient", "edit_patient")

    assert values == _expected_values(
        "edit_patient_seed", "edit_patient", specialist_id=str(seed["specialist_nutritionist"])
    )


def test_edit_patient_form_keeps_the_values_of_a_complete_record(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int], seed: SeedData
) -> None:
    """Check that a patient with every field filled renders the same values as before, hours included.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param seed: Ids of the fake records.
    """
    url = _url(app, "patients.edit_patient", id=complete_patient["patient"])

    values = dict(form_entries(_html(client_admin, url), "form.edit-patient-form"))

    assert values == _expected_values(
        "edit_patient_complete", "edit_patient", specialist_id=str(seed["specialist_other"])
    )


def test_edit_patient_form_keeps_the_values_of_special_records(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int], seed: SeedData
) -> None:
    """Check the edit form of a patient with seconds in the hour and of one without specialist, e-mail and CPF.

    The patient without specialist shows the first one, as the browser selects the first option.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param seed: Ids of the fake records.
    """
    seconds = case_patients(**SECONDS_PATIENT, specialist="specialist_other")
    nospec = case_patients(**NO_SPECIALIST_PATIENT, specialist=None)

    for patient_id, key, specialist_id in (
        (seconds, "edit_patient_seconds", int(seed["specialist_other"])),
        (nospec, "edit_patient_nospec", _first_specialist_id(app)),
    ):
        url = _url(app, "patients.edit_patient", id=patient_id)
        values = dict(form_entries(_html(client_admin, url), "form.edit-patient-form"))
        assert values == _expected_values(key, "edit_patient", specialist_id=str(specialist_id)), key


def _first_specialist_id(app: Flask) -> int:
    """Find the id of the first specialist, which a browser selects when a patient has none.

    :param app: Flask application.
    :return: The lowest specialist id.
    """
    with app.app_context():
        return int(db.session.query(func.min(Specialists.id)).scalar())


def test_anthro_forms_keep_the_values_the_server_renders(
    client_admin: FlaskClient, pages: dict[str, tuple[str, str]]
) -> None:
    """Check the values the new and edit evaluation forms render before their scripts compute anything.

    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    """
    add_values = _rendered_values(client_admin, pages, "add_anthro", "add_anthro")
    edit_values = _rendered_values(client_admin, pages, "edit_anthro", "edit_anthro")

    assert add_values == _expected_values("add_anthro_initial", "add_anthro")
    assert edit_values == _expected_values("edit_anthro_fixed", "edit_anthro")


def test_skinfold_forms_keep_the_values_the_server_renders(
    app: Flask, client_admin: FlaskClient, pages: dict[str, tuple[str, str]], seed: SeedData
) -> None:
    """Check the values of the new bioimpedance form (with and without an earlier measurement) and of the edit form.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param pages: URL and form selector of each page.
    :param seed: Ids of the fake records.
    """
    first_url = _url(app, "patients.add_skinfold", patient_id=int(seed["patient_schedule"]))

    existing = _rendered_values(client_admin, pages, "add_skinfold", "add_skinfold")
    first = dict(form_entries(_html(client_admin, first_url), "form.add-skinfold-form"))
    edit = _rendered_values(client_admin, pages, "edit_skinfold", "edit_skinfold")

    added = {name: ADDED_FIELD_RENDERED_VALUES[name] for name in ADDED_FIELDS["add_skinfold"]}
    assert existing == {**FORM_VALUES["add_skinfold_existing"], **added}
    assert first == {**FORM_VALUES["add_skinfold_first"], **added}
    assert edit == {**FORM_VALUES["edit_skinfold_fixed"], **added}


@pytest.fixture
def edit_target(app: Flask, case_patients: Callable[..., int]) -> int:
    """Create a temporary patient the edit tests may change freely, with every field filled.

    :param app: Flask application.
    :param case_patients: Factory of temporary patients.
    :return: The id of the patient.
    """
    from tests.patient_cases import COMPLETE_PATIENT

    return case_patients(**{**COMPLETE_PATIENT, "name": "Paciente Edicao Completo", "cpf": "333.666.999-57"})


@pytest.mark.parametrize(
    "field, value, key",
    [
        ("objective", "Objetivo alterado", "complete_objective"),
        ("water", "3.5", "complete_water"),
        ("intestine", "9", "complete_intestine"),
        ("email", "novo.email@example.com", "complete_email"),
    ],
)
def test_editing_one_field_changes_only_that_field(
    app: Flask, client_admin: FlaskClient, edit_target: int, field: str, value: str, key: str
) -> None:
    """Check the round trip of the edit page: open it, change one field and save, and only that field changes.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param edit_target: Id of the temporary patient.
    :param field: Field to change.
    :param value: New value typed in the field.
    :param key: Key of the recorded change.
    """
    url = _url(app, "patients.edit_patient", id=edit_target)
    before = _snapshot(app, Patients, edit_target, PATIENT_COLUMNS)

    response = client_admin.post(url, data=_post_values(client_admin, url, "form.edit-patient-form", {field: value}))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(_url(app, "patients.list_patients"))
    diff = changed_columns(before, _snapshot(app, Patients, edit_target, PATIENT_COLUMNS))
    assert diff == EDIT_PATIENT_DIFFS[key]
    assert list(diff) == [field]


def test_saving_the_edit_page_without_changes_keeps_the_data(
    app: Flask, client_admin: FlaskClient, edit_target: int
) -> None:
    """Check that saving a complete record untouched changes nothing.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param edit_target: Id of the temporary patient.
    """
    url = _url(app, "patients.edit_patient", id=edit_target)
    before = _snapshot(app, Patients, edit_target, PATIENT_COLUMNS)

    client_admin.post(url, data=_post_values(client_admin, url, "form.edit-patient-form", {}))

    assert changed_columns(before, _snapshot(app, Patients, edit_target, PATIENT_COLUMNS)) == {}
    assert EDIT_PATIENT_DIFFS["complete_unchanged"] == {}


def test_saving_records_with_empty_fields_normalizes_them_as_before(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check what an untouched save writes for records with missing data, which the old page also wrote.

    Empty texts become empty strings, hours lose their seconds and a patient without specialist gets the first one.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    plain = case_patients("Paciente Campos Nulos", cpf="000.000.000-77", email="nulos@test.local")
    seconds = case_patients(**SECONDS_PATIENT, specialist="specialist_other")
    nospec = case_patients(**{**NO_SPECIALIST_PATIENT, "name": "Paciente Sem Profissional Dois"}, specialist=None)

    results = {}
    for label, patient_id in (("seed", plain), ("seconds", seconds), ("nospec", nospec)):
        url = _url(app, "patients.edit_patient", id=patient_id)
        before = _snapshot(app, Patients, patient_id, PATIENT_COLUMNS)
        client_admin.post(url, data=_post_values(client_admin, url, "form.edit-patient-form", {}))
        results[label] = changed_columns(before, _snapshot(app, Patients, patient_id, PATIENT_COLUMNS))

    assert results["seed"] == EDIT_PATIENT_DIFFS["seed_unchanged"]
    assert results["seconds"] == EDIT_PATIENT_DIFFS["seconds_unchanged"]
    assert results["nospec"] == {
        **EDIT_PATIENT_DIFFS["nospec_unchanged"],
        "specialist_id": [None, _first_specialist_id(app)],
    }


@pytest.mark.parametrize("variant", ["sim", "nao"])
def test_new_patient_is_created_with_every_field(
    app: Flask, client_admin: FlaskClient, seed: SeedData, variant: str
) -> None:
    """Check that the new patient form creates a patient with every field, with and without the conditional answers.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    :param variant: Which recorded patient to post.
    """
    stored = STORED_NEW_PATIENT[variant]
    expected = {**stored, **REMOVED_FIELD_STORED_VALUES}
    url = _url(app, "patients.add_patient")
    data = {key: "" if value is None else str(value) for key, value in stored.items() if key not in REMOVED_FIELDS}
    data["phone"] = data.pop("tel_number")
    data["specialist"] = str(seed["specialist_other"])
    data["hours"] = data["hours"][:5]

    try:
        response = client_admin.post(url, data=_post_values(client_admin, url, "form.add-patient-form", data))

        assert response.status_code == 302
        with app.app_context():
            patient = Patients.query.filter_by(name=stored["name"]).one()
            snapshot = row_values(patient, PATIENT_COLUMNS)
        assert snapshot.pop("specialist_id") == int(seed["specialist_other"])
        assert snapshot == expected
    finally:
        with app.app_context():
            Patients.query.filter_by(name=stored["name"]).delete(synchronize_session=False)
            db.session.commit()


def test_new_patient_ignores_a_heartburn_answer_sent_by_an_old_page(
    app: Flask, client_admin: FlaskClient, seed: SeedData
) -> None:
    """Check that an answer posted for the removed question is not stored: the patient gets the empty answer.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    stored = STORED_NEW_PATIENT["nao"]
    url = _url(app, "patients.add_patient")
    data = {key: "" if value is None else str(value) for key, value in stored.items()}
    data["phone"] = data.pop("tel_number")
    data["specialist"] = str(seed["specialist_other"])
    data["heartburn"] = "sim"
    data["name"] = "Paciente Pagina Antiga"
    data["cpf"] = "246.810.121-47"

    try:
        response = client_admin.post(url, data=data)

        assert response.status_code == 302
        with app.app_context():
            assert Patients.query.filter_by(name=data["name"]).one().heartburn == ""
    finally:
        with app.app_context():
            Patients.query.filter_by(name=data["name"]).delete(synchronize_session=False)
            db.session.commit()


def test_editing_a_patient_keeps_the_stored_heartburn_answer(
    app: Flask, client_admin: FlaskClient, edit_target: int
) -> None:
    """Check that saving the edit page leaves the old answer alone, even when an old page still posts the field.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param edit_target: Id of the temporary patient, whose stored answer is "sim".
    """
    url = _url(app, "patients.edit_patient", id=edit_target)
    assert _snapshot(app, Patients, edit_target, PATIENT_COLUMNS)["heartburn"] == "sim"

    plain = client_admin.post(url, data=_post_values(client_admin, url, "form.edit-patient-form", {}))
    stale = client_admin.post(
        url, data=_post_values(client_admin, url, "form.edit-patient-form", {"objective": "Novo", "heartburn": "não"})
    )

    assert plain.status_code == 302 and stale.status_code == 302
    after = _snapshot(app, Patients, edit_target, PATIENT_COLUMNS)
    assert after["heartburn"] == "sim" and after["objective"] == "Novo"


def test_heartburn_question_is_not_asked_or_shown_anywhere(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check that the new patient form, the edit form and the record of a patient answered "sim" do not mention it.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient = complete_patient["patient"]
    assert _snapshot(app, Patients, patient, PATIENT_COLUMNS)["heartburn"] == "sim"

    for endpoint in ("patients.add_patient", "patients.edit_patient", "patients.view_patient"):
        values = {"id": patient} if endpoint != "patients.add_patient" else {}
        html = _html(client_admin, _url(app, endpoint, **values))

        assert "heartburn" not in html, endpoint
        assert "Azia" not in html and "Refluxo" not in html, endpoint


@pytest.mark.parametrize("case", ANTHRO_ADD_CASES, ids=lambda case: case.key)
def test_new_evaluation_stores_the_recorded_values(
    app: Flask,
    client_admin: FlaskClient,
    case_patients: Callable[..., int],
    case: AnthroAddCase,
) -> None:
    """Check that posting the values the old page computed stores the same evaluation as before.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param case: Input set under test.
    """
    skinfolds = [row for row in (case.previous, case.last) if row]
    patient_id = case_patients(f"Caso {case.key}", case.gender, case.birth_date, skinfolds)
    expected = ANTHRO_ADD_EXPECTED[case.key]
    url = _url(app, "patients.add_anthro", patient_id=patient_id)
    computed = {name: value for name, value in expected["after_date"].items() if name != "peso_anterior"}
    overrides = {
        **computed,
        "data_avaliacao": case.evaluation_date,
        "ultima_guia": case.diet,
        "other_name": case.other_name,
        "grau_atv_fisica": "Moderado",
    }

    response = client_admin.post(url, data=_post_values(client_admin, url, "form.add-anthro-form", overrides))

    assert response.status_code == 302
    with app.app_context():
        rows = AnthropometricEvaluation.query.filter_by(patient_id=patient_id).all()
        assert len(rows) == expected["stored_count"] == 1
        assert row_values(rows[0], ANTHRO_COLUMNS) == expected["stored"]


@pytest.mark.parametrize("case", ANTHRO_EDIT_CASES, ids=lambda case: case.key)
def test_edited_evaluation_stores_the_recorded_values(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int], case: AnthroEditCase
) -> None:
    """Check that saving an evaluation edit changes the same columns as the old page did.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case: Input set under test.
    """
    with app.app_context():
        row = AnthropometricEvaluation(patient_id=complete_patient["patient"], **case.stored)
        db.session.add(row)
        db.session.commit()
        evaluation_id = row.id
    expected = ANTHRO_EDIT_EXPECTED[case.key]
    url = _url(app, "patients.edit_anthro", patient_id=complete_patient["patient"], evaluation_id=evaluation_id)
    overrides = {"idade": expected.get("after_date", expected["load"])["idade"]}
    if case.new_date:
        overrides["data_avaliacao"] = case.new_date
    if case.diet:
        overrides.update({"name": case.diet, "other_name": case.other_name})
    before = _snapshot(app, AnthropometricEvaluation, evaluation_id, ANTHRO_COLUMNS)

    response = client_admin.post(url, data=_post_values(client_admin, url, "form.edit-anthro-form", overrides))

    assert response.status_code == 302
    after = _snapshot(app, AnthropometricEvaluation, evaluation_id, ANTHRO_COLUMNS)
    assert changed_columns(before, after) == expected["diff"]


@pytest.mark.parametrize(
    "case", [case for case in SKINFOLD_ADD_CASES if case.key != "invalid_pressure_blocked"], ids=lambda case: case.key
)
def test_new_measurement_stores_the_recorded_values(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int], case: SkinfoldAddCase
) -> None:
    """Check that posting the values typed in the old page stores the same measurement as before.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param case: Input set under test.
    """
    previous = [] if case.previous_height is None else [(date(2026, 8, 1), 80.0, case.previous_height)]
    patient_id = case_patients(f"Caso sk_{case.key}", skinfolds=previous)
    expected = SKINFOLD_ADD_EXPECTED[case.key]
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)
    overrides = {
        "data_medicao": "2026-11-20",
        "altura": expected["typed"]["altura"],
        "peso": expected["typed"]["peso"],
        "pa": expected["typed"]["pa"],
    }

    response = client_admin.post(url, data=_post_values(client_admin, url, "form.add-skinfold-form", overrides))

    assert response.status_code == 302
    with app.app_context():
        rows = SkinFolds.query.filter_by(patient_id=patient_id).order_by(SkinFolds.id).all()
        assert [row_values(row, SKINFOLD_COLUMNS) for row in rows] == expected["stored"]


@pytest.mark.parametrize("case", SKINFOLD_EDIT_CASES, ids=lambda case: case.key)
def test_edited_measurement_stores_the_recorded_values(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int], case: SkinfoldEditCase
) -> None:
    """Check that saving a measurement edit changes the same columns as the old page did.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case: Input set under test.
    """
    with app.app_context():
        row = SkinFolds(patient_id=complete_patient["patient"], **case.stored)
        db.session.add(row)
        db.session.commit()
        skinfold_id = row.id
    expected = SKINFOLD_EDIT_EXPECTED[case.key]
    url = _url(app, "patients.edit_skinfold", patient_id=complete_patient["patient"], skinfold_id=skinfold_id)
    overrides = {"altura": expected["load"]["altura"], **expected["typed"]}
    before = _snapshot(app, SkinFolds, skinfold_id, SKINFOLD_COLUMNS)

    response = client_admin.post(url, data=_post_values(client_admin, url, "form.edit-skinfold-form", overrides))

    assert response.status_code == 302
    after = _snapshot(app, SkinFolds, skinfold_id, SKINFOLD_COLUMNS)
    assert changed_columns(before, after) == expected["diff"]


OBSERVATION_TOO_LONG_MESSAGE = "O campo não pode ter mais de 1000 caracteres."


def _observation(app: Flask, skinfold_id: int) -> str | None:
    """Read the stored observation of a measurement.

    :param app: Flask application.
    :param skinfold_id: Id of the measurement.
    :return: The stored text, or None when the column is NULL.
    """
    return _snapshot(app, SkinFolds, skinfold_id, ("observacoes",))["observacoes"]


def _add_measurement_data(client: FlaskClient, url: str, **overrides: str) -> dict[str, str]:
    """Build the data a browser posts from the new measurement form, with a valid measurement typed in.

    :param client: Test client.
    :param url: URL path of the new measurement page.
    :param overrides: Fields typed or changed by the test, by name.
    :return: The data to post.
    """
    typed = {"data_medicao": "2026-11-20", "altura": "1.7", "peso": "70.5", "pa": "12/8", **overrides}
    return _post_values(client, url, "form.add-skinfold-form", typed)


def _new_measurement_observation(app: Flask, patient_id: int) -> list[str | None]:
    """List the stored observations of the measurements of a patient, by id.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :return: The observation of each measurement.
    """
    with app.app_context():
        rows = SkinFolds.query.filter_by(patient_id=patient_id).order_by(SkinFolds.id).all()
        return [row.observacoes for row in rows]


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("", None),
        ("   \r\n \t ", None),
        ("Alergia a lactose", "Alergia a lactose"),
        ("  Texto com bordas  \r\n", "Texto com bordas"),
        ("linha 1\r\n\r\nlinha 3", "linha 1\n\nlinha 3"),
        ('<b>negrito</b> & "aspas"', '<b>negrito</b> & "aspas"'),
    ],
    ids=["empty", "blank", "text", "stripped", "line_breaks", "markup"],
)
def test_new_measurement_stores_the_observation(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int], typed: str, stored: str | None
) -> None:
    """Check that the new measurement page stores NULL for a blank observation and the stripped text otherwise.

    Line breaks sent by a browser (``\\r\\n``) are stored as ``\\n``.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param typed: Text typed in the observation field.
    :param stored: Value the column must hold.
    """
    patient_id = case_patients("Paciente Observacao Nova")
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)

    response = client_admin.post(url, data=_add_measurement_data(client_admin, url, observacoes=typed))

    assert response.status_code == 302
    assert _new_measurement_observation(app, patient_id) == [stored]


def test_new_measurement_without_the_observation_field_stores_null(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that a page that does not send the field, such as one opened before the change, still saves.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Observacao Ausente")
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)
    data = _add_measurement_data(client_admin, url)
    del data["observacoes"]

    response = client_admin.post(url, data=data)

    assert response.status_code == 302
    assert _new_measurement_observation(app, patient_id) == [None]


@pytest.fixture
def noted_measurement(app: Flask, complete_patient: dict[str, int]) -> dict[str, Any]:
    """Add a measurement with an observation to the complete patient; the fixture of the patient removes it.

    :param app: Flask application.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :return: The ids of the patient and of the measurement.
    """
    with app.app_context():
        row = SkinFolds(patient_id=complete_patient["patient"], **{**FIXED_SKINFOLD, "observacoes": "Nota antiga"})
        db.session.add(row)
        db.session.commit()
        return {"patient": complete_patient["patient"], "skinfold": row.id}


def test_edit_page_shows_saves_and_clears_the_observation(
    app: Flask, client_admin: FlaskClient, noted_measurement: dict[str, Any]
) -> None:
    """Check the round trip of the edit page: the note is shown, an untouched save keeps it, a change replaces it.

    A blank text clears it, which stores NULL again.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param noted_measurement: Ids of the patient and of the measurement with a note.
    """
    skinfold_id = noted_measurement["skinfold"]
    url = _url(app, "patients.edit_skinfold", patient_id=noted_measurement["patient"], skinfold_id=skinfold_id)
    selector = "form.edit-skinfold-form"
    assert dict(form_entries(_html(client_admin, url), selector))["observacoes"] == "Nota antiga"

    for typed, expected in (
        ({}, "Nota antiga"),
        ({"observacoes": "  Nota nova  "}, "Nota nova"),
        ({"observacoes": "   "}, None),
    ):
        response = client_admin.post(url, data=_post_values(client_admin, url, selector, typed))

        assert response.status_code == 302
        assert _observation(app, skinfold_id) == expected, typed
    assert dict(form_entries(_html(client_admin, url), selector))["observacoes"] == ""


def test_edit_page_keeps_the_observation_when_the_field_is_not_sent(
    app: Flask, client_admin: FlaskClient, noted_measurement: dict[str, Any]
) -> None:
    """Check that a page that does not send the field cannot erase a note that was saved meanwhile.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param noted_measurement: Ids of the patient and of the measurement with a note.
    """
    skinfold_id = noted_measurement["skinfold"]
    url = _url(app, "patients.edit_skinfold", patient_id=noted_measurement["patient"], skinfold_id=skinfold_id)
    data = _post_values(client_admin, url, "form.edit-skinfold-form", {"peso": "71"})
    del data["observacoes"]

    response = client_admin.post(url, data=data)

    assert response.status_code == 302
    assert _observation(app, skinfold_id) == "Nota antiga"
    assert _snapshot(app, SkinFolds, skinfold_id, ("peso",)) == {"peso": 71.0}


def test_observation_of_exactly_1000_characters_is_accepted(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check the limit: 1000 characters are stored, even when the browser sends its line break as two characters.

    The browser counts a line break as one character in ``maxlength``, so the text below is 1000 characters long for
    the user and 1001 in the request.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Observacao Limite")
    url = _url(app, "patients.add_skinfold", patient_id=patient_id)
    plain = "a" * 1000
    with_break = "b" * 500 + "\r\n" + "c" * 499

    for typed in (plain, with_break):
        response = client_admin.post(url, data=_add_measurement_data(client_admin, url, observacoes=typed))

        assert response.status_code == 302

    assert _new_measurement_observation(app, patient_id) == [plain, with_break.replace("\r\n", "\n")]


@pytest.mark.parametrize("page", ["add_skinfold", "edit_skinfold"])
def test_observation_longer_than_1000_characters_is_refused_in_portuguese(
    app: Flask,
    client_admin: FlaskClient,
    case_patients: Callable[..., int],
    noted_measurement: dict[str, Any],
    page: str,
) -> None:
    """Check that 1001 characters give the Portuguese message next to the field and save nothing.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param noted_measurement: Ids of the patient and of the measurement with a note.
    :param page: Measurement form under test.
    """
    too_long = "x" * 1001
    if page == "add_skinfold":
        patient_id = case_patients("Paciente Observacao Longa")
        url = _url(app, "patients.add_skinfold", patient_id=patient_id)
        data = _add_measurement_data(client_admin, url, observacoes=too_long)
    else:
        url = _url(
            app,
            "patients.edit_skinfold",
            patient_id=noted_measurement["patient"],
            skinfold_id=noted_measurement["skinfold"],
        )
        data = _post_values(client_admin, url, "form.edit-skinfold-form", {"observacoes": too_long})

    response = client_admin.post(url, data=data)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert OBSERVATION_TOO_LONG_MESSAGE in body and too_long in body
    if page == "add_skinfold":
        assert _new_measurement_observation(app, patient_id) == []
    else:
        assert _observation(app, noted_measurement["skinfold"]) == "Nota antiga"
