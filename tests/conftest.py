"""Shared fixtures: temporary-database app, fake seed data and role-authenticated clients."""

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from tests.aliases import ClientFactory, SeedData
from tests.constants import (
    ALEMBIC_REVISION,
    EMAILS,
    FIXTURE_DIET_URL,
    FORMULAS,
    NUTRITIONIST_USERNAME,
    RECOVERY_CODES,
    ROLES,
    SECRETS,
    TEST_PASSWORD,
    TRICKY_TEXT,
)
from tests.pdf_fixtures import SIZES, make_pdf

_TMP_DIR = Path(tempfile.mkdtemp(prefix="emagreser-tests-"))
_TEMP_UPLOAD_DIR = _TMP_DIR / "temp_files"
os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{_TMP_DIR / 'test.db'}"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    """Remove the temporary directory when the test session ends.

    :param session: pytest session.
    :param exitstatus: Exit status of the session.
    """
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def app() -> Iterator[Flask]:
    """Create the Flask app on the temporary SQLite database and seed it.

    The database URI is always overwritten (never setdefault) before config is imported, and checked again here before
    create_app() runs db.create_all(). The process tempdir and the email "local" domain rule are adjusted for the
    session, and unhandled view errors become 500 responses so known failures can be recorded as expected statuses.

    :raises AssertionError: If the configuration does not point to the temporary SQLite database.
    :return: The configured Flask application (yielded; the session adjustments are undone afterwards).
    """
    import email_validator

    import config
    from app import create_app

    assert (
        str(_TMP_DIR) in config.Config.SQLALCHEMY_DATABASE_URI
    ), "the config is not pointing to the temporary SQLite database"

    original_tempdir = tempfile.tempdir
    tempfile.tempdir = str(_TMP_DIR)

    local_was_blocked = "local" in email_validator.SPECIAL_USE_DOMAIN_NAMES
    if local_was_blocked:
        email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("local")

    flask_app = create_app()
    assert flask_app.config["SQLALCHEMY_DATABASE_URI"] == os.environ["SQLALCHEMY_DATABASE_URI"]
    assert str(_TMP_DIR) in flask_app.config["SQLALCHEMY_DATABASE_URI"], "tests may only use the temporary SQLite"

    _TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    flask_app.config["TEMP_UPLOAD_FOLDER"] = str(_TEMP_UPLOAD_DIR)
    flask_app.config["TESTING"] = True
    flask_app.config["PROPAGATE_EXCEPTIONS"] = False
    flask_app.config["WTF_CSRF_ENABLED"] = False

    flask_app.extensions["tests_seed"] = _seed(flask_app)
    yield flask_app

    tempfile.tempdir = original_tempdir
    if local_was_blocked:
        email_validator.SPECIAL_USE_DOMAIN_NAMES.append("local")


def _seed(flask_app: Flask) -> SeedData:
    """Create the fake roles, users, specialists, patients, records and diets.

    Patient 1 belongs to the nutritionist's specialist, patient 2 has a future schedule with the nutritionist and
    patient 3 has no relation to the nutritionist.

    :param flask_app: Flask application bound to the temporary database.
    :return: Ids (and file names) of the created records, keyed by a short name.
    """
    from flask_security.utils import hash_password

    from app.models import AnthropometricEvaluation, Diet, Patients, Role, Schedules, SkinFolds, Specialists, db

    datastore = flask_app.extensions["security"].datastore
    now = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(second=0, microsecond=0, tzinfo=None)
    future_dt = (now + timedelta(days=10)).replace(hour=10, minute=0)
    past_dt = (now - timedelta(days=10)).replace(hour=10, minute=0)

    with flask_app.app_context():
        for role_name in ROLES:
            db.session.add(Role(name=role_name))
        db.session.commit()

        users = {}
        for role_name in ROLES:
            username = NUTRITIONIST_USERNAME if role_name == "nutritionist" else f"Usuario Teste {role_name}"
            user = datastore.create_user(
                email=EMAILS[role_name],
                username=username,
                password=hash_password(TEST_PASSWORD),
                roles=[role_name],
            )
            users[role_name] = user
        db.session.commit()

        specialist_nutritionist = Specialists(
            name=NUTRITIONIST_USERNAME,
            cpf="000.000.000-01",
            tel_number="(31) 90000-0001",
            email=EMAILS["nutritionist"],
        )
        specialist_other = Specialists(
            name="Profissional Teste 2", cpf="000.000.000-02", tel_number="(31) 90000-0002", email="prof2@test.local"
        )
        db.session.add_all([specialist_nutritionist, specialist_other])
        db.session.commit()

        def make_patient(number: int, specialist: Specialists) -> Patients:
            """Build a fake patient assigned to a specialist.

            :param number: Patient number (1 to 3), used in the name, birth date, CPF, phone and email.
            :param specialist: Specialist the patient is assigned to.
            :return: The unsaved patient.
            """
            return Patients(
                name=f"Paciente Teste {number}",
                gender="feminino",
                birth_date=date(1990, 1, number),
                cpf=f"000.000.000-1{number}",
                tel_number=f"(31) 91111-000{number}",
                email=f"paciente{number}@test.local",
                specialist_id=specialist.id,
                medication="não",
                intestine=7,
                allergies="não",
                water=2.0,
                heartburn="não",
                physical_activities="não",
                frequency=0,
                objective="Objetivo ficticio de teste",
            )

        patient_nutritionist = make_patient(1, specialist_nutritionist)
        patient_schedule = make_patient(2, specialist_other)
        patient_other = make_patient(3, specialist_other)
        db.session.add_all([patient_nutritionist, patient_schedule, patient_other])
        db.session.commit()

        anthro = AnthropometricEvaluation(
            patient_id=patient_nutritionist.id,
            data_avaliacao=(now - timedelta(days=30)).date(),
            ultima_guia="Dieta Detox",
            idade=34,
            evolucao="Evolucao ficticia",
            p_max=80.0,
            p_ide=62.0,
            p_min=55.0,
            imc=24.2,
            nutri_class="Normal",
            necessidade_calorica="1800 kcal",
            ingestao_liquido=2.1,
            grau_atv_fisica="Moderado",
            specialist_name=NUTRITIONIST_USERNAME,
        )
        skinfold = SkinFolds(
            patient_id=patient_nutritionist.id,
            data_medicao=(now - timedelta(days=30)).date(),
            altura=1.70,
            peso=70.0,
            massa_muscular=30.0,
            gordura=25.0,
            abdominal=80.0,
            cintura=75.0,
            quadril=95.0,
            idade_metabolica=33,
            pa="12/8",
        )
        schedule_future = Schedules(
            patient_id=patient_schedule.id, date_time=future_dt, specialist=NUTRITIONIST_USERNAME, status="pendente"
        )
        schedule_past = Schedules(
            patient_id=patient_nutritionist.id, date_time=past_dt, specialist=NUTRITIONIST_USERNAME, status="finalizado"
        )
        db.session.add_all([anthro, skinfold, schedule_future, schedule_past])

        diet_a4 = Diet(name="Dieta Teste A4", description="Dieta ficticia (e2e)", diet_file=FIXTURE_DIET_URL, order=1)
        diet_edited = Diet(
            name="Dieta Teste Editada",
            description="Dieta ficticia com edicao salva",
            diet_file="https://fixtures.test/diet-edited.pdf",
            order=2,
        )
        diet_backend = Diet(
            name="Dieta Teste Backend",
            description="Dieta ficticia usada pelos testes do backend do editor",
            diet_file="https://fixtures.test/diet-backend.pdf",
            order=3,
        )
        db.session.add_all([diet_a4, diet_edited, diet_backend])
        db.session.commit()

        edited_filename = f"dieta_personalizada_id_{diet_edited.id}.pdf"
        (_TEMP_UPLOAD_DIR / edited_filename).write_bytes(make_pdf(*SIZES["a4_596x842"]))
        diet_edited.temp_diet_file = edited_filename
        db.session.commit()

        return {
            "user_admin": users["admin"].id,
            "user_secretary": users["secretary"].id,
            "user_nutritionist": users["nutritionist"].id,
            "specialist_nutritionist": specialist_nutritionist.id,
            "specialist_other": specialist_other.id,
            "patient_nutritionist": patient_nutritionist.id,
            "patient_schedule": patient_schedule.id,
            "patient_other": patient_other.id,
            "anthro": anthro.id,
            "skinfold": skinfold.id,
            "schedule_future": schedule_future.id,
            "schedule_past": schedule_past.id,
            "schedule_future_date": future_dt.date().isoformat(),
            "diet_a4": diet_a4.id,
            "diet_edited": diet_edited.id,
            "diet_edited_file": edited_filename,
            "diet_backend": diet_backend.id,
        }


@pytest.fixture(scope="session")
def seed(app: Flask) -> SeedData:
    """Provide the ids and file names of the fake records created in the temporary SQLite.

    :param app: Flask application.
    :return: A copy of the seed dictionary.
    """
    return dict(app.extensions["tests_seed"])


def login(client: FlaskClient, role: str) -> TestResponse:
    """Log in through the real /login form (Flask-Security).

    :param client: Flask test client.
    :param role: Role whose fake user logs in.
    :return: The response of the login POST.
    :raises AssertionError: If the login does not redirect.
    """
    response = client.post("/login", data={"email": EMAILS[role], "password": TEST_PASSWORD})
    assert response.status_code == 302, f"login of {role} failed: {response.status_code}"
    return response


@pytest.fixture(scope="session")
def _session_cookies(app: Flask) -> dict[str, str]:
    """Log in once per role (bcrypt is slow) and keep the session cookies.

    :param app: Flask application.
    :return: The session cookie value of each role.
    """
    cookies = {}
    for role in ROLES:
        client = app.test_client()
        login(client, role)
        cookies[role] = client.get_cookie("session").value
    return cookies


@pytest.fixture
def client_for(app: Flask, _session_cookies: dict[str, str]) -> ClientFactory:
    """Provide a factory of new test clients: client_for("anonymous" | "admin" | "secretary" | "nutritionist").

    :param app: Flask application.
    :param _session_cookies: Session cookie value of each role.
    :return: The client factory.
    """

    def factory(role: str = "anonymous") -> FlaskClient:
        """Create a test client, authenticated unless the role is anonymous.

        :param role: Role of the client.
        :return: A new Flask test client.
        """
        client = app.test_client()
        if role != "anonymous":
            client.set_cookie("session", _session_cookies[role])
        return client

    return factory


@pytest.fixture
def client(client_for: ClientFactory) -> FlaskClient:
    """Provide an anonymous test client.

    :param client_for: Factory of test clients by role.
    :return: A new anonymous test client.
    """
    return client_for("anonymous")


@pytest.fixture
def client_admin(client_for: ClientFactory) -> FlaskClient:
    """Provide a test client logged in as admin.

    :param client_for: Factory of test clients by role.
    :return: A new admin test client.
    """
    return client_for("admin")


@pytest.fixture
def client_secretary(client_for: ClientFactory) -> FlaskClient:
    """Provide a test client logged in as secretary.

    :param client_for: Factory of test clients by role.
    :return: A new secretary test client.
    """
    return client_for("secretary")


@pytest.fixture
def client_nutritionist(client_for: ClientFactory) -> FlaskClient:
    """Provide a test client logged in as nutritionist.

    :param client_for: Factory of test clients by role.
    :return: A new nutritionist test client.
    """
    return client_for("nutritionist")


@pytest.fixture
def set_superusers(app: Flask) -> Iterator[Callable[[str], None]]:
    """Provide a function that sets the superuser e-mails of the app for one test.

    The session app starts with no superuser, and the setting is restored when the test ends.

    :param app: Flask application.
    :return: The function that receives the ``SUPERUSER_EMAILS`` value (yielded; the previous value is restored).
    """
    previous = app.config.get("SUPERUSER_EMAILS")

    def setter(value: str) -> None:
        """Set the superuser e-mails.

        :param value: Text in the format of the ``SUPERUSER_EMAILS`` setting.
        """
        app.config["SUPERUSER_EMAILS"] = value

    yield setter
    app.config["SUPERUSER_EMAILS"] = previous


@pytest.fixture
def tricky_rows(app: Flask) -> Iterator[dict[str, Any]]:
    """Add temporary rows with hostile text, NULLs, odd numbers and secrets, and remove them afterwards.

    :param app: Flask application.
    :return: The ids of the rows (yielded; the rows are deleted at the end of the test).
    """
    from app.models import Diet, Patients, Role, SkinFolds, User, db

    with app.app_context():
        diets = [Diet(name=TRICKY_TEXT, description="descrição", diet_file=None)]
        diets += [
            Diet(name=f"{prefix}fórmula", description=prefix, order=index) for index, prefix in enumerate(FORMULAS)
        ]
        role = Role(name="papel-de-teste", description=None, permissions=["ler", "escrever"])
        user = User(
            email="segredos@test.local",
            username="Usuario Segredos",
            active=True,
            password=SECRETS["password"],
            fs_uniquifier=SECRETS["fs_uniquifier"],
            fs_webauthn_user_handle=SECRETS["fs_webauthn_user_handle"],
            tf_totp_secret=SECRETS["tf_totp_secret"],
            us_totp_secrets=SECRETS["us_totp_secrets"],
            mf_recovery_codes=RECOVERY_CODES,
        )
        patient = Patients(
            name=TRICKY_TEXT,
            gender="feminino",
            birth_date=date(1985, 3, 9),
            tel_number="(31) 90000-0000",
            medication="não",
            intestine=3,
            allergies="não",
            water=72.5,
            heartburn="não",
            physical_activities="sim",
            hours=time(7, 30, 5),
            started_at=datetime(2025, 1, 2, 3, 4, 5, 123456),
            frequency=2,
            objective="=Objetivo",
        )
        db.session.add_all([*diets, role, user, patient])
        db.session.commit()
        skinfold = SkinFolds(
            patient_id=patient.id,
            data_medicao=date(2026, 1, 2),
            altura=0.1 + 0.2,
            peso=float("inf"),
            massa_muscular=-float("inf"),
            pa="12/8",
        )
        db.session.add(skinfold)
        db.session.commit()
        ids = {
            "diets": [diet.id for diet in diets],
            "role": role.id,
            "user": user.id,
            "patient": patient.id,
            "skinfold": skinfold.id,
        }
    yield ids
    with app.app_context():
        SkinFolds.query.filter_by(id=ids["skinfold"]).delete(synchronize_session=False)
        Diet.query.filter(Diet.id.in_(ids["diets"])).delete(synchronize_session=False)
        Role.query.filter_by(id=ids["role"]).delete(synchronize_session=False)
        User.query.filter_by(id=ids["user"]).delete(synchronize_session=False)
        Patients.query.filter_by(id=ids["patient"]).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def complete_patient(app: Flask, seed: SeedData) -> Iterator[dict[str, int]]:
    """Add a patient with every field filled, a fixed evaluation and a fixed measurement, and remove them afterwards.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The ids of the patient, evaluation and measurement (yielded; the rows are deleted at the end of the test).
    """
    from app.models import AnthropometricEvaluation, Patients, SkinFolds, db
    from tests.patient_cases import COMPLETE_PATIENT, FIXED_EVALUATION, FIXED_SKINFOLD

    with app.app_context():
        patient = Patients(**COMPLETE_PATIENT, specialist_id=int(seed["specialist_other"]))
        db.session.add(patient)
        db.session.commit()
        evaluation = AnthropometricEvaluation(patient_id=patient.id, **FIXED_EVALUATION)
        skinfold = SkinFolds(patient_id=patient.id, **FIXED_SKINFOLD)
        db.session.add_all([evaluation, skinfold])
        db.session.commit()
        ids = {"patient": patient.id, "evaluation": evaluation.id, "skinfold": skinfold.id}
    yield ids
    with app.app_context():
        SkinFolds.query.filter_by(patient_id=ids["patient"]).delete(synchronize_session=False)
        AnthropometricEvaluation.query.filter_by(patient_id=ids["patient"]).delete(synchronize_session=False)
        Patients.query.filter_by(id=ids["patient"]).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def case_patients(app: Flask, seed: SeedData) -> Iterator[Callable[..., int]]:
    """Provide a factory of temporary patients with measurements; every patient it created is removed afterwards.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The factory (yielded; the created patients and their rows are deleted at the end of the test).
    """
    from app.models import AnthropometricEvaluation, Patients, Schedules, SkinFolds, db

    created: list[int] = []

    def create(
        name: str,
        gender: str = "feminino",
        birth_date: date = date(1990, 1, 1),
        skinfolds: Sequence[tuple[date, float, float]] = (),
        specialist: str | None = "specialist_other",
        **overrides: Any,
    ) -> int:
        """Create a patient and its bioimpedance measurements.

        :param name: Name of the patient.
        :param gender: Gender of the patient.
        :param birth_date: Birth date of the patient.
        :param skinfolds: Measurements to add, each one as (date, weight, height).
        :param specialist: Seed key of the specialist the patient belongs to, or None for no specialist.
        :param overrides: Other columns of the patient.
        :return: The id of the new patient.
        """
        values: dict[str, Any] = {
            "name": name,
            "gender": gender,
            "birth_date": birth_date,
            "cpf": None,
            "tel_number": "(31) 92222-0000",
            "email": None,
            "specialist_id": int(seed[specialist]) if specialist else None,
            "medication": "não",
            "intestine": 7,
            "allergies": "não",
            "water": 2.0,
            "heartburn": "não",
            "physical_activities": "não",
            "frequency": 0,
            "objective": "Objetivo ficticio de teste",
        }
        values.update(overrides)
        with app.app_context():
            patient = Patients(**values)
            db.session.add(patient)
            db.session.commit()
            for when, weight, height in skinfolds:
                db.session.add(
                    SkinFolds(
                        patient_id=patient.id,
                        data_medicao=when,
                        altura=height,
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
            created.append(patient.id)
            return patient.id

    yield create
    with app.app_context():
        for patient_id in created:
            SkinFolds.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            AnthropometricEvaluation.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            Schedules.query.filter_by(patient_id=patient_id).delete(synchronize_session=False)
            Patients.query.filter_by(id=patient_id).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def alembic_table(app: Flask) -> Iterator[str]:
    """Create the Alembic version table, which the test database does not have, and drop it afterwards.

    :param app: Flask application.
    :return: The revision stored in the table (yielded; the table is dropped at the end of the test).
    """
    from app.models import db

    with app.app_context(), db.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_REVISION}')")
    yield ALEMBIC_REVISION
    with app.app_context(), db.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
