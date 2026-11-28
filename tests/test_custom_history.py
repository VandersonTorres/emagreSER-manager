"""Custom history page: values kept for complete patients, patients without measurements or evaluations, and access."""

from collections.abc import Callable, Iterator
from datetime import date

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from app import models
from tests.aliases import ClientFactory, SeedData
from tests.history_baselines import HISTORY_RECORDED
from tests.history_cases import (
    HISTORY_CASES,
    NO_MEASUREMENTS_CASE,
    SPECIALIST_EMAIL,
    SPECIALIST_NAME,
    HistoryCase,
    create_history_patient,
    read_history,
)

CHART_URL_PART = "Chart.js"
NOTICE = "Ainda não há bioimpedância registrada."


@pytest.fixture
def history_patient(app: Flask, seed: SeedData) -> Iterator[Callable[..., int]]:
    """Provide a factory of patients with the evaluations and measurements of a case, removed after the test.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The factory (yielded; the created patients and their rows are deleted at the end of the test).
    """
    created: list[int] = []

    def create(case: HistoryCase, specialist: str = "specialist_other") -> int:
        """Create the patient of a case.

        :param case: Case to create.
        :param specialist: Seed key of the specialist the patient belongs to.
        :return: The id of the new patient.
        """
        with app.app_context():
            patient_id = create_history_patient(models, case, int(seed[specialist]))
        created.append(patient_id)
        return patient_id

    yield create
    with app.app_context():
        for patient_id in created:
            models.SkinFolds.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            models.AnthropometricEvaluation.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            models.Patients.query.filter_by(id=patient_id).delete(synchronize_session=False)
        models.db.session.commit()


def _history_url(app: Flask, patient_id: int) -> str:
    """Build the URL of the custom history of a patient.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for("patients.view_custom_history", id=patient_id, pat_name="Paciente")


def _record_url(app: Flask, patient_id: int) -> str:
    """Build the URL of the record of a patient.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for("patients.view_patient", id=patient_id)


def _open(app: Flask, client: FlaskClient, patient_id: int) -> str:
    """Open the custom history of a patient, which must answer 200.

    :param app: Flask application.
    :param client: Test client.
    :param patient_id: Id of the patient.
    :return: The HTML of the page.
    """
    response = client.get(_history_url(app, patient_id))
    assert response.status_code == 200, f"history of {patient_id}: {response.status_code}"
    return response.get_data(as_text=True)


def test_recorded_cases_use_the_seeded_specialist(app: Flask, seed: SeedData) -> None:
    """Check that the specialist written in the recorded values is the one the cases are created with.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.app_context():
        specialist = models.db.session.get(models.Specialists, int(seed["specialist_other"]))
        assert (specialist.name, specialist.email) == (SPECIALIST_NAME, SPECIALIST_EMAIL)


@pytest.mark.parametrize("case", HISTORY_CASES, ids=lambda case: case.key)
def test_history_with_measurements_shows_the_recorded_values(
    app: Flask, client_admin: FlaskClient, history_patient: Callable[..., int], case: HistoryCase
) -> None:
    """Check that a patient with evaluations and measurements still gets the same values and texts.

    The cases cover one evaluation, gain, loss and unchanged weight, fat and muscle filled and empty, measurements
    entered out of order, a weight equal to the maximum and a patient without CPF and specialist.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param history_patient: Factory of patients with the records of a case.
    :param case: Case under test.
    """
    html = _open(app, client_admin, history_patient(case))

    assert read_history(html) == HISTORY_RECORDED[case.key]


def test_history_with_measurements_has_no_notice_and_keeps_the_chart(
    app: Flask, client_admin: FlaskClient, history_patient: Callable[..., int]
) -> None:
    """Check that the notice of missing bioimpedance never shows up for a patient with measurements.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param history_patient: Factory of patients with the records of a case.
    """
    soup = BeautifulSoup(_open(app, client_admin, history_patient(HISTORY_CASES[1])), "html.parser")

    assert NOTICE not in soup.get_text()
    assert soup.select_one("canvas#evolutionsChart") is not None
    assert soup.select_one("script[src*='chart.umd.min.js']") is not None


def test_history_without_measurements_answers_200_with_the_notice(
    app: Flask, client_admin: FlaskClient, history_patient: Callable[..., int]
) -> None:
    """Check the patient with evaluations and no measurement: what comes from the evaluations and a clear notice.

    The values that depend on the measurements are not shown, there is no chart and no Chart.js script.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param history_patient: Factory of patients with the records of a case.
    """
    patient_id = history_patient(NO_MEASUREMENTS_CASE)

    soup = BeautifulSoup(_open(app, client_admin, patient_id), "html.parser")

    notice = soup.select_one(".alert[role=status]")
    assert notice is not None and NOTICE in notice.get_text()
    link = notice.select_one("a")
    with app.test_request_context():
        assert link is not None and link["href"] == url_for("patients.add_skinfold", patient_id=patient_id)
    summary = {label: value for label, value in read_history(str(soup))["summary"]}
    assert summary["Idade"] == "39" and summary["1ª avaliação física"] == "10/02/2026"
    details = {label: value for label, value in read_history(str(soup))["details"]}
    assert details == {"IMC atual": "22.1", "Peso ideal": "59.5", "Peso máximo": "71.5"}
    text = soup.get_text(" ", strip=True)
    for label in ("Altura", "Peso inicial", "Peso atual", "Resultado final", "Percentual de gordura"):
        assert label not in text, label
    assert "None" not in text
    assert soup.select_one("canvas") is None and soup.select_one(".history-message") is None
    assert soup.select("script[src*='chart']") == [soup.select_one("script[src$='js/chart_config.js']")]
    assert CHART_URL_PART not in str(soup)
    assert soup.select_one("button[data-print]") is not None
    assert soup.select_one("h1.page-header-title").get_text(strip=True) == "Histórico personalizado"
    assert soup.select_one(".page-header-subtitle").get_text(strip=True) == NO_MEASUREMENTS_CASE.name


@pytest.mark.parametrize("with_measurements", [False, True], ids=["nothing", "only_measurements"])
def test_history_without_evaluations_has_a_header_and_a_way_back(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int], with_measurements: bool
) -> None:
    """Check the page of a patient without evaluations: title, name, link back to the record, new evaluation action.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param with_measurements: Whether the patient has measurements, which alone do not make a history.
    """
    measurements = [(date(2026, 5, 1), 70.0, 1.7)] if with_measurements else []
    patient_id = case_patients("Paciente Sem Avaliacao Historico", skinfolds=measurements)

    soup = BeautifulSoup(_open(app, client_admin, patient_id), "html.parser")

    assert soup.select_one("h1.page-header-title").get_text(strip=True) == "Histórico personalizado"
    assert soup.select_one(".page-header-subtitle").get_text(strip=True) == "Paciente Sem Avaliacao Historico"
    back = soup.select_one("a.page-header-back")
    assert back is not None and back["href"] == f"{_record_url(app, patient_id)}#evolucao"
    empty = soup.select_one(".empty-state")
    assert empty is not None and "ainda não possui avaliações" in empty.get_text()
    action = empty.select_one("a")
    with app.test_request_context():
        new_evaluation_url = url_for("patients.add_anthro", patient_id=patient_id)
    assert action is not None and action.get_text(strip=True) == "Nova avaliação"
    assert action["href"] == new_evaluation_url
    assert soup.select_one("canvas") is None and soup.select_one("button[data-print]") is None
    assert CHART_URL_PART not in str(soup) and NOTICE not in soup.get_text()


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_every_role_opens_the_history_of_a_patient_without_measurements(
    app: Flask, client_for: ClientFactory, history_patient: Callable[..., int], role: str
) -> None:
    """Check that the three roles open the new page, the nutritionist for a patient of their own.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param history_patient: Factory of patients with the records of a case.
    :param role: Role under test.
    """
    patient_id = history_patient(NO_MEASUREMENTS_CASE, specialist="specialist_nutritionist")

    html = _open(app, client_for(role), patient_id)

    assert NOTICE in html


def test_nutritionist_still_cannot_open_the_history_of_other_patients(
    app: Flask, seed: SeedData, client_for: ClientFactory, history_patient: Callable[..., int]
) -> None:
    """Check that the access rules did not change: the nutritionist is sent back to the list for a patient of others.

    The patient with a future schedule with the nutritionist is still allowed.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param history_patient: Factory of patients with the records of a case.
    """
    other = history_patient(NO_MEASUREMENTS_CASE, specialist="specialist_other")
    nutritionist = client_for("nutritionist")

    refused = nutritionist.get(_history_url(app, other))
    scheduled = nutritionist.get(_history_url(app, int(seed["patient_schedule"])))
    unrelated = nutritionist.get(_history_url(app, int(seed["patient_other"])))
    anonymous = client_for("anonymous").get(_history_url(app, other))

    assert refused.status_code == 302 and refused.headers["Location"].endswith("/patients")
    assert scheduled.status_code == 200
    assert unrelated.status_code == 302 and unrelated.headers["Location"].endswith("/patients")
    assert anonymous.status_code == 403
    assert client_for("admin").get(_history_url(app, other)).status_code == 200
