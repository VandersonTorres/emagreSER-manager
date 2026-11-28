"""Records and input sets of the patient page tests, whose recorded results are in tests/patient_baselines.py.

The baselines keep what the pages did when they were recorded. The intended differences are the fields the clinic no
longer asks (``REMOVED_FIELDS``): the tests take them out of the recorded names and values, and a new patient gets the
empty answer listed in ``REMOVED_FIELD_STORED_VALUES``; and the fields the pages ask now and the recording did not have
(``ADDED_FIELDS``, by page): the tests add them to the recorded names, and ``ADDED_FIELD_RENDERED_VALUES`` holds what a
page renders in them when the stored row has nothing there.
"""

from dataclasses import dataclass
from datetime import date, time
from typing import Any

REMOVED_FIELDS: frozenset[str] = frozenset({"heartburn"})
REMOVED_FIELD_STORED_VALUES: dict[str, str] = {"heartburn": ""}
ADDED_FIELDS: dict[str, frozenset[str]] = {
    "add_skinfold": frozenset({"observacoes"}),
    "edit_skinfold": frozenset({"observacoes"}),
}
ADDED_FIELD_RENDERED_VALUES: dict[str, str] = {"observacoes": ""}

COMPLETE_PATIENT: dict[str, Any] = {
    "name": "Paciente Completo Base",
    "gender": "masculino",
    "birth_date": date(1980, 7, 20),
    "cpf": "111.444.777-35",
    "tel_number": "(11) 98888-7777",
    "email": "completo@example.com",
    "medication": "sim",
    "medications_details": "Losartana",
    "intestine": 5,
    "allergies": "sim",
    "allergies_details": "Camarão",
    "water": 2.5,
    "heartburn": "sim",
    "physical_activities": "sim",
    "physical_details": "Musculação",
    "hours": time(18, 30),
    "frequency": 3,
    "objective": "Hipertrofia e saúde",
}

SECONDS_PATIENT: dict[str, Any] = {
    **COMPLETE_PATIENT,
    "name": "Paciente Segundos",
    "cpf": "222.555.888-46",
    "hours": time(7, 30, 5),
}

NO_SPECIALIST_PATIENT: dict[str, Any] = {
    **COMPLETE_PATIENT,
    "name": "Paciente Sem Profissional",
    "cpf": None,
    "email": None,
    "medications_details": None,
    "allergies_details": None,
    "physical_details": None,
    "hours": None,
}

PATIENT_COLUMNS: tuple[str, ...] = (
    "name",
    "gender",
    "birth_date",
    "cpf",
    "tel_number",
    "email",
    "specialist_id",
    "medication",
    "medications_details",
    "intestine",
    "allergies",
    "allergies_details",
    "water",
    "heartburn",
    "physical_activities",
    "physical_details",
    "hours",
    "frequency",
    "objective",
)
ANTHRO_COLUMNS: tuple[str, ...] = (
    "data_avaliacao",
    "ultima_guia",
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
    "specialist_name",
)
SKINFOLD_COLUMNS: tuple[str, ...] = (
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
)

FIXED_EVALUATION: dict[str, Any] = {
    "data_avaliacao": date(2026, 5, 10),
    "ultima_guia": "Dieta Detox",
    "idade": 99,
    "evolucao": "perdeu 1.00 kg",
    "p_max": 80.0,
    "p_ide": 66.0,
    "p_min": 57.0,
    "imc": 24.2,
    "nutri_class": "Peso normal",
    "necessidade_calorica": "2450 Kcal/ Dia (Manutenção)",
    "ingestao_liquido": 2.45,
    "grau_atv_fisica": "Moderado",
    "specialist_name": "Nutri Base",
}

FIXED_SKINFOLD: dict[str, Any] = {
    "data_medicao": date(2026, 5, 10),
    "altura": 1.7,
    "peso": 70.0,
    "massa_muscular": 30.0,
    "gordura": 25.0,
    "abdominal": 80.0,
    "cintura": 75.0,
    "quadril": 95.0,
    "idade_metabolica": 33,
    "pa": "12/8",
}


@dataclass(frozen=True)
class AnthroAddCase:
    """Input set of the new evaluation page: a patient with its last (and optionally previous) measurement.

    :param key: Short name, used in the patient name and the test id.
    :param gender: Gender of the patient.
    :param birth_date: Birth date of the patient.
    :param previous: Measurement before the last one as (date, weight, height), or None.
    :param last: Last measurement as (date, weight, height); the page reads weight and height from it.
    :param evaluation_date: Date typed in the evaluation date field (ISO format).
    :param diet: Option chosen in the diet select.
    :param other_name: Name typed when the diet is "Outro".
    """

    key: str
    gender: str
    birth_date: date
    previous: tuple[date, float, float] | None
    last: tuple[date, float, float]
    evaluation_date: str
    diet: str
    other_name: str = ""


ANTHRO_ADD_CASES: tuple[AnthroAddCase, ...] = (
    AnthroAddCase(
        "low_bmi_first",
        "feminino",
        date(1990, 6, 15),
        None,
        (date(2026, 10, 1), 52.0, 1.70),
        "2026-11-24",
        "Dieta Detox",
    ),
    AnthroAddCase(
        "normal_bmi_loss",
        "masculino",
        date(1985, 3, 10),
        (date(2026, 8, 1), 72.5, 1.75),
        (date(2026, 10, 1), 70.0, 1.75),
        "2026-11-24",
        "Dieta Low Carb I",
    ),
    AnthroAddCase(
        "overweight_elderly",
        "feminino",
        date(1948, 9, 9),
        None,
        (date(2026, 10, 1), 62.35, 1.58),
        "2026-09-08",
        "Dieta Guia N2",
    ),
    AnthroAddCase(
        "obese_gain_other_diet",
        "masculino",
        date(1975, 12, 31),
        (date(2026, 6, 1), 90.0, 1.78),
        (date(2026, 10, 1), 95.4, 1.78),
        "2027-01-01",
        "Outro",
        "Dieta Personalizada Teste",
    ),
    AnthroAddCase(
        "child_same_weight",
        "feminino",
        date(2016, 2, 29),
        (date(2025, 11, 1), 38.2, 1.45),
        (date(2026, 1, 15), 38.2, 1.45),
        "2026-02-28",
        "Dieta Violeta",
    ),
    AnthroAddCase(
        "obese_class_two_loss",
        "masculino",
        date(1960, 5, 20),
        (date(2026, 5, 1), 120.55, 1.72),
        (date(2026, 10, 1), 118.0, 1.72),
        "2026-11-24",
        "Dieta Termogênico N3",
    ),
    AnthroAddCase(
        "obese_class_three_height_in_cm",
        "masculino",
        date(1992, 8, 1),
        None,
        (date(2026, 10, 1), 135.0, 165.0),
        "2026-11-24",
        "Dieta Zero Açucar",
    ),
    AnthroAddCase(
        "normal_bmi_decimals",
        "feminino",
        date(2001, 10, 10),
        (date(2026, 7, 1), 60.2, 1.67),
        (date(2026, 10, 1), 61.7, 1.67),
        "2026-10-09",
        "Dieta Primavera",
    ),
)


@dataclass(frozen=True)
class AnthroEditCase:
    """Input set of the evaluation edit page: a stored evaluation and what the user changes.

    :param key: Short name, used in the test id.
    :param stored: Column values of the stored evaluation (the patient is the complete patient).
    :param new_date: Date typed in the evaluation date field, or None to leave it as loaded.
    :param diet: Option chosen in the diet select, or None to leave it as loaded.
    :param other_name: Name typed when the diet is "Outro".
    """

    key: str
    stored: dict[str, Any]
    new_date: str | None = None
    diet: str | None = None
    other_name: str = ""


ANTHRO_EDIT_CASES: tuple[AnthroEditCase, ...] = (
    AnthroEditCase("unchanged", FIXED_EVALUATION),
    AnthroEditCase("new_date", FIXED_EVALUATION, new_date="2027-07-19"),
    AnthroEditCase("other_diet", FIXED_EVALUATION, new_date="2026-07-20", diet="Outro", other_name="Guia Nova Teste"),
    AnthroEditCase(
        "unknown_diet_and_empty_texts",
        {**FIXED_EVALUATION, "ultima_guia": "Guia Antiga Removida", "evolucao": None, "necessidade_calorica": None},
    ),
)

SKINFOLD_PA_INPUTS: tuple[str, ...] = (
    "12/8",
    "120/80",
    "9/6",
    "12",
    "1200/80",
    "12/800",
    "abc",
    "30/29",
    "29/30",
    "",
    " 13/9 ",
    "999/99",
    "30/30",
)
SKINFOLD_WEIGHT_INPUTS: tuple[str, ...] = ("62,5", "62.5", "1.234,5", "70,", ",5", "80")


@dataclass(frozen=True)
class SkinfoldAddCase:
    """Input set of the new bioimpedance page.

    :param key: Short name, used in the patient name and the test id.
    :param previous_height: Height of an earlier measurement of the patient, or None when there is none.
    :param height: Height typed when there is no earlier measurement.
    :param weight: Weight typed.
    :param pa: Blood pressure typed.
    """

    key: str
    previous_height: float | None
    height: str
    weight: str
    pa: str


SKINFOLD_ADD_CASES: tuple[SkinfoldAddCase, ...] = (
    SkinfoldAddCase("first_comma_valid", None, "1.62", "58,4", "12/8"),
    SkinfoldAddCase("previous_height_in_cm", 165.0, "", "70.5", "13/9"),
    SkinfoldAddCase("invalid_pressure_blocked", None, "1.6", "60", "12"),
)


@dataclass(frozen=True)
class SkinfoldEditCase:
    """Input set of the bioimpedance edit page.

    :param key: Short name, used in the test id.
    :param stored: Column values of the stored measurement (the patient is the complete patient).
    :param weight: Weight typed, or None to leave it as loaded.
    :param pa: Blood pressure typed, or None to leave it as loaded.
    """

    key: str
    stored: dict[str, Any]
    weight: str | None = None
    pa: str | None = None


SKINFOLD_EDIT_CASES: tuple[SkinfoldEditCase, ...] = (
    SkinfoldEditCase("unchanged", FIXED_SKINFOLD),
    SkinfoldEditCase("height_in_cm", {**FIXED_SKINFOLD, "altura": 165.0}),
    SkinfoldEditCase("comma_weight_invalid_pressure", FIXED_SKINFOLD, weight="71,3", pa="12"),
)
