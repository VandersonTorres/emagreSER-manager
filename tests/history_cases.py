"""Patients and a reader for the custom history page, whose recorded results are in tests/history_baselines.py."""

import json
from dataclasses import dataclass
from datetime import date
from types import ModuleType

from bs4 import BeautifulSoup

SPECIALIST_NAME = "Profissional Teste 2"
SPECIALIST_EMAIL = "prof2@test.local"


@dataclass(frozen=True)
class HistoryCase:
    """A patient with evaluations and bioimpedance measurements for the custom history page.

    Each evaluation is (date, age, BMI, ideal weight, maximum weight) and each measurement is (date, height, weight,
    muscle mass, fat), in insertion order.
    """

    key: str
    cpf: str | None
    with_specialist: bool
    evaluations: tuple[tuple[date, int, float, float, float], ...]
    skinfolds: tuple[tuple[date, float, float, float, float], ...]

    @property
    def name(self) -> str:
        """Build the patient name from the key.

        :return: The name of the patient.
        """
        return f"Paciente Historico {self.key}"


HISTORY_CASES: tuple[HistoryCase, ...] = (
    HistoryCase(
        key="single_evaluation",
        cpf="000.000.000-21",
        with_specialist=True,
        evaluations=((date(2026, 5, 10), 34, 24.2, 62.0, 80.0),),
        skinfolds=((date(2026, 5, 10), 1.70, 70.0, 30.0, 25.0),),
    ),
    HistoryCase(
        key="gain",
        cpf="000.000.000-22",
        with_specialist=True,
        evaluations=(
            (date(2026, 1, 10), 40, 22.5, 60.5, 70.0),
            (date(2026, 3, 10), 40, 23.1, 60.5, 72.0),
            (date(2026, 5, 10), 41, 23.8, 61.25, 74.5),
        ),
        skinfolds=(
            (date(2026, 1, 10), 1.62, 62.5, 28.0, 24.5),
            (date(2026, 3, 10), 1.62, 64.0, 0.0, 25.0),
            (date(2026, 5, 10), 1.62, 66.75, 0.0, 0.0),
        ),
    ),
    HistoryCase(
        key="loss",
        cpf="000.000.000-23",
        with_specialist=True,
        evaluations=(
            (date(2026, 2, 1), 52, 31.0, 68.0, 78.0),
            (date(2026, 4, 1), 52, 29.4, 68.0, 78.0),
        ),
        skinfolds=(
            (date(2026, 2, 1), 1.68, 90.0, 41.0, 38.0),
            (date(2026, 3, 1), 1.68, 86.5, 40.5, 36.5),
            (date(2026, 4, 1), 1.68, 83.25, 40.0, 35.0),
            (date(2026, 5, 1), 1.68, 80.1, 39.5, 33.0),
        ),
    ),
    HistoryCase(
        key="unchanged",
        cpf="000.000.000-24",
        with_specialist=True,
        evaluations=(
            (date(2026, 3, 5), 29, 22.0, 58.0, 66.0),
            (date(2026, 6, 5), 29, 22.0, 58.0, 66.0),
        ),
        skinfolds=(
            (date(2026, 3, 5), 1.65, 70.0, 0.0, 0.0),
            (date(2026, 6, 5), 1.65, 70.0, 0.0, 0.0),
        ),
    ),
    HistoryCase(
        key="out_of_order",
        cpf=None,
        with_specialist=False,
        evaluations=(
            (date(2026, 7, 1), 33, 26.0, 64.0, 82.0),
            (date(2026, 9, 1), 33, 25.1, 64.0, 82.0),
        ),
        skinfolds=(
            (date(2026, 9, 1), 1.75, 78.0, 35.0, 0.0),
            (date(2026, 7, 1), 1.74, 81.5, 0.0, 0.0),
            (date(2026, 8, 1), 1.75, 79.9, 34.0, 0.0),
        ),
    ),
    HistoryCase(
        key="at_maximum_weight",
        cpf="000.000.000-26",
        with_specialist=True,
        evaluations=((date(2026, 5, 20), 45, 27.5, 63.0, 75.5),),
        skinfolds=((date(2026, 5, 20), 1.66, 75.5, 33.3, 31.2),),
    ),
)


NO_MEASUREMENTS_CASE = HistoryCase(
    key="no_measurements",
    cpf="000.000.000-27",
    with_specialist=True,
    evaluations=(
        (date(2026, 2, 10), 38, 21.4, 59.0, 70.0),
        (date(2026, 4, 10), 39, 22.1, 59.5, 71.5),
    ),
    skinfolds=(),
)


def create_history_patient(models: ModuleType, case: HistoryCase, specialist_id: int | None) -> int:
    """Create a patient with the evaluations and measurements of a case.

    :param models: The ``app.models`` module of the app under test.
    :param case: Case to create.
    :param specialist_id: Id of the specialist the patient belongs to; ignored when the case has none.
    :return: The id of the new patient.
    """
    session = models.db.session
    patient = models.Patients(
        name=case.name,
        gender="feminino",
        birth_date=date(1985, 6, 15),
        cpf=case.cpf,
        tel_number="(31) 93333-0000",
        specialist_id=specialist_id if case.with_specialist else None,
        medication="não",
        intestine=7,
        allergies="não",
        water=2.0,
        heartburn="não",
        physical_activities="não",
        frequency=0,
        objective="Objetivo ficticio de teste",
    )
    session.add(patient)
    session.commit()
    for when, age, imc, ideal, maximum in case.evaluations:
        session.add(
            models.AnthropometricEvaluation(
                patient_id=patient.id,
                data_avaliacao=when,
                idade=age,
                p_max=maximum,
                p_ide=ideal,
                p_min=ideal - 5,
                imc=imc,
                nutri_class="Peso normal",
                ingestao_liquido=2.0,
                grau_atv_fisica="Moderado",
            )
        )
    for when, height, weight, muscle, fat in case.skinfolds:
        session.add(
            models.SkinFolds(
                patient_id=patient.id,
                data_medicao=when,
                altura=height,
                peso=weight,
                massa_muscular=muscle,
                gordura=fat,
                abdominal=0,
                cintura=0,
                quadril=0,
                idade_metabolica=0,
                pa="12/8",
            )
        )
    session.commit()
    return patient.id


def _pairs(soup: BeautifulSoup, selector: str) -> list[list[str]]:
    """Read the label and value of each item of a description list.

    :param soup: Parsed page.
    :param selector: CSS selector of the description list.
    :return: The [label, value] pairs in document order.
    """
    return [
        [item.select_one("dt").get_text(" ", strip=True), item.select_one("dd").get_text(" ", strip=True)]
        for item in soup.select(f"{selector} > div")
    ]


def read_history(html: str) -> dict[str, object]:
    """Read the values a custom history page shows, in a form that can be compared and recorded.

    :param html: HTML of the page.
    :return: The title, header, summary, details, chart data, closing message and the whole text of the content.
    """
    soup = BeautifulSoup(html, "html.parser")
    canvas = soup.select_one("canvas#evolutionsChart")
    message = soup.select_one(".history-message")
    return {
        "title": soup.title.get_text(),
        "heading": soup.select_one("h1.page-header-title").get_text(strip=True),
        "subtitle": soup.select_one(".page-header-subtitle").get_text(strip=True),
        "summary": _pairs(soup, "dl.detail-grid"),
        "details": _pairs(soup, "dl.stat-grid"),
        "dates": json.loads(canvas["data-dates"]) if canvas else None,
        "weights": json.loads(canvas["data-weights"]) if canvas else None,
        "message": message.get_text(strip=True) if message else None,
        "content": soup.select_one(".app-content").get_text(" ", strip=True),
    }
