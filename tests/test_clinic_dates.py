"""Dates of the clinic: defaults evaluated when a row is inserted and the São Paulo display of stored UTC times."""

from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta, timezone, tzinfo

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from app import dates, models
from tests.aliases import SeedData

Freeze = Callable[[datetime], None]
UTC_PLUS_NINE = timezone(timedelta(hours=9))
SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))


@pytest.fixture
def freeze_clock(monkeypatch: pytest.MonkeyPatch) -> Freeze:
    """Provide a function that freezes the clock the model defaults read at an instant.

    :param monkeypatch: Pytest monkeypatch fixture.
    :return: The function that receives the frozen instant, a time with time zone.
    """

    def freeze(instant: datetime) -> None:
        """Make ``datetime.now`` of the dates module answer a fixed instant.

        :param instant: The frozen instant, with time zone.
        """

        class FrozenDatetime(datetime):
            """Datetime whose ``now`` is fixed."""

            @classmethod
            def now(cls, tz: tzinfo | None = None) -> datetime:
                """Return the frozen instant in the requested time zone.

                :param tz: Time zone of the result; when missing, the instant without time zone.
                :return: The frozen instant.
                """
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(dates, "datetime", FrozenDatetime)

    return freeze


@pytest.fixture
def new_rows(app: Flask, seed: SeedData) -> Iterator[Callable[..., dict[str, int]]]:
    """Provide a factory of a patient with an evaluation and a measurement that set no date, removed after the test.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The factory (yielded; the created rows are deleted at the end of the test).
    """
    created: list[int] = []

    def create(name: str, evaluation_date: date | None = None, measurement_date: date | None = None) -> dict[str, int]:
        """Insert a patient, an evaluation and a measurement, leaving the dates to the defaults unless they are given.

        :param name: Name of the patient.
        :param evaluation_date: Date of the evaluation, or None to use the default.
        :param measurement_date: Date of the measurement, or None to use the default.
        :return: The ids of the patient, the evaluation and the measurement.
        """
        with app.app_context():
            patient = models.Patients(
                name=name,
                gender="feminino",
                birth_date=date(1990, 1, 1),
                tel_number="(31) 94444-0000",
                specialist_id=int(seed["specialist_other"]),
                medication="não",
                intestine=1,
                allergies="não",
                water=1.0,
                heartburn="",
                physical_activities="não",
                objective="Objetivo ficticio de teste",
            )
            models.db.session.add(patient)
            models.db.session.commit()
            evaluation = models.AnthropometricEvaluation(
                patient_id=patient.id,
                data_avaliacao=evaluation_date,
                idade=30,
                p_max=80.0,
                p_ide=62.0,
                p_min=55.0,
                imc=24.0,
                nutri_class="Peso normal",
                ingestao_liquido=2.0,
                grau_atv_fisica="Moderado",
            )
            skinfold = models.SkinFolds(
                patient_id=patient.id, data_medicao=measurement_date, altura=1.7, peso=70.0, pa="12/8"
            )
            models.db.session.add_all([evaluation, skinfold])
            models.db.session.commit()
            created.append(patient.id)
            return {"patient": patient.id, "evaluation": evaluation.id, "skinfold": skinfold.id}

    yield create
    with app.app_context():
        for patient_id in created:
            models.SkinFolds.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            models.AnthropometricEvaluation.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            models.Patients.query.filter_by(id=patient_id).delete(synchronize_session=False)
        models.db.session.commit()


def _stored(app: Flask, ids: dict[str, int]) -> dict[str, object]:
    """Read the date columns of the rows back from the database.

    :param app: Flask application.
    :param ids: Ids returned by the ``new_rows`` factory.
    :return: The registration time, the evaluation date and the measurement date.
    """
    with app.app_context():
        return {
            "started_at": models.db.session.get(models.Patients, ids["patient"]).started_at,
            "data_avaliacao": models.db.session.get(models.AnthropometricEvaluation, ids["evaluation"]).data_avaliacao,
            "data_medicao": models.db.session.get(models.SkinFolds, ids["skinfold"]).data_medicao,
        }


def test_the_three_defaults_are_callables_not_values_fixed_at_import() -> None:
    """Check that the columns hold a function to call at each insert instead of one value computed when loading."""
    columns = (
        models.Patients.__table__.c.started_at,
        models.AnthropometricEvaluation.__table__.c.data_avaliacao,
        models.SkinFolds.__table__.c.data_medicao,
    )

    assert [column.default.is_callable for column in columns] == [True, True, True]


def test_started_at_is_the_utc_time_of_each_insert(
    app: Flask, freeze_clock: Freeze, new_rows: Callable[..., dict[str, int]]
) -> None:
    """Check that each new patient gets the time of its own insert, as naive UTC, and not the time of the first one.

    :param app: Flask application.
    :param freeze_clock: Function that freezes the clock.
    :param new_rows: Factory of rows that set no date.
    """
    freeze_clock(datetime(2031, 3, 4, 1, 30, 15, tzinfo=timezone.utc))
    first = new_rows("Paciente Relogio Um")
    freeze_clock(datetime(2031, 3, 5, 15, 45, 10, tzinfo=timezone.utc))
    second = new_rows("Paciente Relogio Dois")

    assert _stored(app, first)["started_at"] == datetime(2031, 3, 4, 1, 30, 15)
    assert _stored(app, second)["started_at"] == datetime(2031, 3, 5, 15, 45, 10)


@pytest.mark.parametrize(
    "instant, expected",
    [
        (datetime(2031, 3, 4, 1, 30, tzinfo=timezone.utc), date(2031, 3, 3)),
        (datetime(2031, 3, 4, 2, 59, 59, tzinfo=timezone.utc), date(2031, 3, 3)),
        (datetime(2031, 3, 4, 3, 0, tzinfo=timezone.utc), date(2031, 3, 4)),
        (datetime(2031, 3, 4, 12, 0, tzinfo=timezone.utc), date(2031, 3, 4)),
    ],
    ids=["01h30_utc", "just_before_midnight", "midnight_in_sao_paulo", "noon_utc"],
)
def test_evaluation_and_measurement_dates_default_to_today_in_sao_paulo_at_insert_time(
    app: Flask,
    freeze_clock: Freeze,
    new_rows: Callable[..., dict[str, int]],
    instant: datetime,
    expected: date,
) -> None:
    """Check that both date defaults follow the clock of the insert and use the date of São Paulo, not the UTC one.

    :param app: Flask application.
    :param freeze_clock: Function that freezes the clock.
    :param new_rows: Factory of rows that set no date.
    :param instant: Frozen instant of the insert.
    :param expected: Date the rows must get.
    """
    freeze_clock(instant)

    stored = _stored(app, new_rows("Paciente Datas Padrao"))

    assert stored["data_avaliacao"] == expected and stored["data_medicao"] == expected


def test_a_date_sent_by_the_form_is_not_replaced_by_the_default(
    app: Flask, freeze_clock: Freeze, new_rows: Callable[..., dict[str, int]]
) -> None:
    """Check that the defaults only fill missing values: dates given when inserting are stored as they are.

    :param app: Flask application.
    :param freeze_clock: Function that freezes the clock.
    :param new_rows: Factory of rows that may set their dates.
    """
    freeze_clock(datetime(2031, 3, 4, 1, 30, tzinfo=timezone.utc))

    stored = _stored(app, new_rows("Paciente Datas Informadas", date(2026, 5, 10), date(2026, 5, 11)))

    assert stored["data_avaliacao"] == date(2026, 5, 10) and stored["data_medicao"] == date(2026, 5, 11)


@pytest.mark.parametrize(
    "value, expected",
    [
        (datetime(2026, 11, 25, 1, 30), "24/11/2026"),
        (datetime(2026, 11, 25, 12, 0), "25/11/2026"),
        (datetime(2026, 11, 25, 2, 59, 59), "24/11/2026"),
        (datetime(2026, 11, 25, 3, 0), "25/11/2026"),
        (datetime(2026, 11, 25, 1, 30, tzinfo=timezone.utc), "24/11/2026"),
        (datetime(2026, 11, 24, 23, 0, tzinfo=SAO_PAULO_OFFSET), "24/11/2026"),
        (datetime(2026, 11, 25, 10, 0, tzinfo=UTC_PLUS_NINE), "24/11/2026"),
        (datetime(2026, 1, 1, 2, 0), "31/12/2025"),
        (None, ""),
    ],
    ids=[
        "naive_01h30",
        "naive_noon",
        "naive_before_midnight",
        "naive_midnight",
        "aware_utc",
        "aware_sao_paulo",
        "aware_other_zone",
        "new_year",
        "none",
    ],
)
def test_stored_times_are_shown_as_the_date_in_sao_paulo(value: datetime | None, expected: str) -> None:
    """Check the display helper with naive UTC values, values with their own time zone and a missing value.

    :param value: Stored time.
    :param expected: Text the clinic must see.
    """
    assert dates.format_clinic_date(value) == expected


def test_the_display_helper_is_the_clinic_date_template_filter(app: Flask) -> None:
    """Check that the helper is registered as the ``clinic_date`` filter of the templates.

    :param app: Flask application.
    """
    assert app.jinja_env.filters["clinic_date"] is dates.format_clinic_date


def test_utc_now_has_no_time_zone_and_clinic_today_is_a_date() -> None:
    """Check the two clock helpers: a naive UTC time and the date of São Paulo."""
    now = dates.utc_now()
    today = dates.clinic_today()

    assert now.tzinfo is None and abs(now - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(seconds=5)
    assert type(today) is date and abs(today - datetime.now(dates.CLINIC_TIMEZONE).date()) <= timedelta(days=1)


@pytest.mark.parametrize(
    "started_at, expected",
    [
        (datetime(2026, 11, 25, 1, 30), "24/11/2026"),
        (datetime(2026, 11, 25, 12, 0), "25/11/2026"),
        (None, "Não informado"),
    ],
    ids=["after_21h_in_sao_paulo", "midday", "without_value"],
)
def test_record_shows_paciente_desde_in_sao_paulo(
    app: Flask,
    client_admin: FlaskClient,
    case_patients: Callable[..., int],
    started_at: datetime | None,
    expected: str,
) -> None:
    """Check the "Paciente desde" fact of the record, which used to show the UTC date.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param started_at: Stored registration time, naive UTC.
    :param expected: Text the record must show.
    """
    patient_id = case_patients("Paciente Desde", started_at=started_at)
    if started_at is None:
        with app.app_context():
            models.Patients.query.filter_by(id=patient_id).update({"started_at": None})
            models.db.session.commit()
    with app.test_request_context():
        url = url_for("patients.view_patient", id=patient_id)

    soup = BeautifulSoup(client_admin.get(url).get_data(as_text=True), "html.parser")

    facts = {
        fact.select_one("dt").get_text(): fact.select_one("dd").get_text(strip=True)
        for fact in soup.select(".patient-fact")
    }
    assert facts["Paciente desde"] == expected
