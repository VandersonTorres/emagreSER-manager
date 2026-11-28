"""Apply the migration of the bioimpedance observation to a real PostgreSQL server, the way the release step does.

These tests never run by default. They need a PostgreSQL server (version 16, like the production one) in the
MIGRATION_TEST_DATABASE_URL environment variable and the git program, and they run with "pytest -m pg_migration".
Every test creates a fresh database with a unique name, builds the schema of the revision before the migration in it,
and drops it at the end.

The old chain of migrations cannot build a database from nothing (its first steps alter tables that the application
created, and every ``flask`` command creates the missing tables from the current models before it migrates). So the
schema of the previous revision comes from the models of ``OLD_SCHEMA_COMMIT``, read with ``git archive`` into a scratch
folder, and ``flask db stamp`` marks the database with that revision, as it is in production.
"""

import os
import shlex
import subprocess
import sys
import tarfile
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from app.models import db

pytestmark = pytest.mark.pg_migration

ROOT = Path(__file__).resolve().parent.parent
PROCFILE = ROOT / "Procfile"
ENV_VAR = "MIGRATION_TEST_DATABASE_URL"
ENV_EXAMPLE = "postgresql://postgres:PASSWORD@127.0.0.1:55433/postgres"  # pragma: allowlist secret
OLD_SCHEMA_COMMIT = "a516612546eef148a2ffd1d105cac52fad461701"  # pragma: allowlist secret
PREVIOUS_REVISION = "fb739ba57804"  # pragma: allowlist secret
NOTES_REVISION = "03f89a0c5fa6"  # pragma: allowlist secret
COMMAND_TIMEOUT_SECONDS = 180
OLD_SCHEMA_CODE = (
    "import os, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from sqlalchemy import create_engine\n"
    "from app.models import db\n"
    "engine = create_engine(os.environ['SQLALCHEMY_DATABASE_URI'])\n"
    "db.metadata.create_all(engine)\n"
    "engine.dispose()\n"
)
MEASUREMENT: dict[str, Any] = {
    "id": 1,
    "patient_id": 1,
    "data_medicao": date(2026, 5, 10),
    "altura": 1.7,
    "peso": 70.5,
    "massa_muscular": 30.0,
    "gordura": 25.0,
    "abdominal": 80.0,
    "cintura": 75.0,
    "quadril": 95.0,
    "idade_metabolica": 33,
    "pa": "12/8",
}
INSERT_PATIENT = text(
    "INSERT INTO patients (id, name, gender, birth_date, tel_number, medication, intestine, allergies, water, "
    "heartburn, physical_activities, frequency, objective) VALUES (1, 'Paciente Migracao', 'feminino', '1990-01-01', "
    "'(31) 90000-0000', 'não', 7, 'não', 2.0, '', 'não', 0, 'Objetivo ficticio')"
)
INSERT_MEASUREMENT = text(
    "INSERT INTO skinfolds (id, patient_id, data_medicao, altura, peso, massa_muscular, gordura, abdominal, cintura, "
    "quadril, idade_metabolica, pa) VALUES (:id, :patient_id, :data_medicao, :altura, :peso, :massa_muscular, "
    ":gordura, :abdominal, :cintura, :quadril, :idade_metabolica, :pa)"
)

DatabaseFactory = Callable[[str], URL]


@dataclass(frozen=True)
class PreviousDatabase:
    """A throwaway database with the schema of the revision before the migration and one measurement.

    :param url: URL of the database.
    :param password: Password of the server, hidden from the messages of failed commands.
    """

    url: URL
    password: str


def server_url() -> URL:
    """Read the URL of the PostgreSQL server and check that git is available.

    Every test asks for it through its fixtures, so a missing setting stops each test with an error, never a skip.

    :raises pytest.fail.Exception: If the environment variable or git is missing; the tests never skip.
    :return: The URL of a database of the server, used to create the temporary databases.
    """
    value = os.environ.get(ENV_VAR)
    if not value:
        pytest.fail(
            f"{ENV_VAR} is not set. Point it to a PostgreSQL server, for example "
            f"{ENV_VAR}={ENV_EXAMPLE} (see tests/README.md).",
            pytrace=False,
        )
    if subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0:
        pytest.fail(
            "The git program is not installed or not in the PATH, and the migration tests need it.", pytrace=False
        )
    return make_url(value).set(drivername="postgresql")


@pytest.fixture
def new_database() -> Iterator[DatabaseFactory]:
    """Provide a function that creates empty databases with unique names, and drop them all afterwards.

    :return: The function that receives a short tag and returns the URL of the new database (yielded).
    """
    created: list[str] = []
    admin: list[Engine] = []

    def create(tag: str) -> URL:
        """Create an empty database on the server of the environment variable.

        :param tag: Short text added to the database name, to ease the debugging.
        :return: The URL of the new database.
        """
        url = server_url()
        if not admin:
            admin.append(create_engine(url, isolation_level="AUTOCOMMIT"))
        name = f"emagreser_migration_{uuid.uuid4().hex[:10]}_{tag}"
        with admin[0].connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created.append(name)
        return url.set(database=name)

    yield create
    if admin:
        with admin[0].connect() as connection:
            for name in created:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin[0].dispose()


def _environment(url: URL) -> dict[str, str]:
    """Build the environment of the commands: the virtualenv first in the PATH, no .env file, the throwaway database.

    :param url: URL of the throwaway database.
    :return: The environment variables.
    """
    path = f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
    return {
        **os.environ,
        "PATH": path,
        "FLASK_SKIP_DOTENV": "1",
        "SQLALCHEMY_DATABASE_URI": url.render_as_string(hide_password=False),
    }


def _run(args: list[str], database: PreviousDatabase, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run a command against the throwaway database and fail with its output, without the password, if it fails.

    :param args: The command and its arguments.
    :param database: The throwaway database.
    :param cwd: Folder where the command runs.
    :return: The finished process.
    :raises AssertionError: If the command exits with an error.
    """
    result = subprocess.run(
        args,
        env=_environment(database.url),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    output = (result.stdout + result.stderr).replace(database.password, "***")
    assert result.returncode == 0, f"{shlex.join(args)} exited with {result.returncode}:\n{output}"
    return result


def _release_command() -> list[str]:
    """Read the release command of the Procfile, which Heroku runs before a new release goes live.

    :return: The command and its arguments.
    """
    lines = PROCFILE.read_text(encoding="utf-8").splitlines()
    (command,) = [line.partition(":")[2].strip() for line in lines if line.startswith("release:")]
    return shlex.split(command)


def _flask(*arguments: str) -> list[str]:
    """Build a ``flask --app run db`` command, the way the Procfile runs it.

    :param arguments: Arguments of ``flask db``, such as ``downgrade``.
    :return: The command and its arguments.
    """
    return ["flask", "--app", "run", "db", *arguments]


def _engine(url: URL) -> Engine:
    """Create an engine for the throwaway database.

    :param url: URL of the database.
    :return: The engine; the caller disposes of it.
    """
    return create_engine(url)


def _skinfolds_columns(url: URL) -> dict[str, tuple[str, str, str | None]]:
    """Read the columns of the skinfolds table from the catalog of the server.

    :param url: URL of the database.
    :return: The column name mapped to (data type, nullable, default).
    """
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'skinfolds' ORDER BY ordinal_position"
                )
            ).all()
    finally:
        engine.dispose()
    return {name: (data_type, nullable, default) for name, data_type, nullable, default in rows}


def _current_revision(url: URL) -> str | None:
    """Read the revision stored in the Alembic table.

    :param url: URL of the database.
    :return: The revision, or None when the table is empty.
    """
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    finally:
        engine.dispose()


def _measurement_row(url: URL) -> dict[str, Any]:
    """Read the stored measurement, with the observation when the column exists.

    :param url: URL of the database.
    :return: The columns of the only row of skinfolds.
    """
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            return dict(connection.execute(text("SELECT * FROM skinfolds")).mappings().one())
    finally:
        engine.dispose()


@pytest.fixture
def previous_database(new_database: DatabaseFactory, tmp_path: Path) -> PreviousDatabase:
    """Create a database with the schema of the revision before the migration, stamped, with one measurement.

    :param new_database: Function that creates empty databases.
    :param tmp_path: Temporary folder of the test, where the models of the old commit are read.
    :return: The database, ready for the release command.
    """
    url = new_database("notes")
    password = url.password or ""
    database = PreviousDatabase(url, password)
    tree = tmp_path / "previous-tree"
    tree.mkdir()
    archive = tmp_path / "previous-tree.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", f"--output={archive}", OLD_SCHEMA_COMMIT]
        + [":(glob)app/**/*.py", ":(glob)scripts/**/*.py", "config.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    with tarfile.open(archive) as bundle:
        bundle.extractall(tree, filter="data")
    assert "observacoes" not in (tree / "app" / "models.py").read_text(encoding="utf-8")

    _run([sys.executable, "-c", OLD_SCHEMA_CODE, str(tree)], database, cwd=tmp_path)
    _run(_flask("stamp", PREVIOUS_REVISION), database)
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(INSERT_PATIENT)
            connection.execute(INSERT_MEASUREMENT, MEASUREMENT)
    finally:
        engine.dispose()
    assert "observacoes" not in _skinfolds_columns(url)
    assert _current_revision(url) == PREVIOUS_REVISION
    return database


def test_release_command_adds_the_observation_column(previous_database: PreviousDatabase) -> None:
    """Run the release command of the Procfile on the previous schema: the column appears as nullable text, no default.

    :param previous_database: Database with the schema of the previous revision.
    """
    _run(_release_command(), previous_database)

    assert _skinfolds_columns(previous_database.url)["observacoes"] == ("text", "YES", None)
    assert _current_revision(previous_database.url) == NOTES_REVISION


def test_release_command_keeps_the_stored_measurement_with_a_null_observation(
    previous_database: PreviousDatabase,
) -> None:
    """Check that the measurement saved before the migration is intact and has no observation afterwards.

    :param previous_database: Database with the schema of the previous revision.
    """
    _run(_release_command(), previous_database)

    row = _measurement_row(previous_database.url)
    assert row.pop("observacoes") is None
    assert row == MEASUREMENT


def test_release_command_can_run_again_without_changes(previous_database: PreviousDatabase) -> None:
    """Check that a second release, which Heroku runs on every deploy, ends well and changes nothing.

    :param previous_database: Database with the schema of the previous revision.
    """
    _run(_release_command(), previous_database)
    columns = _skinfolds_columns(previous_database.url)
    row = _measurement_row(previous_database.url)

    _run(_release_command(), previous_database)

    assert _skinfolds_columns(previous_database.url) == columns
    assert _measurement_row(previous_database.url) == row
    assert _current_revision(previous_database.url) == NOTES_REVISION


def test_downgrade_drops_the_column_and_a_new_upgrade_adds_it_back(previous_database: PreviousDatabase) -> None:
    """Check the way back: ``flask db downgrade`` drops the column, keeps the measurement, and an upgrade restores it.

    :param previous_database: Database with the schema of the previous revision.
    """
    url = previous_database.url
    _run(_release_command(), previous_database)
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE skinfolds SET observacoes = 'Nota que será descartada'"))
    finally:
        engine.dispose()

    _run(_flask("downgrade"), previous_database)

    assert "observacoes" not in _skinfolds_columns(url)
    assert _current_revision(url) == PREVIOUS_REVISION
    assert _measurement_row(url) == MEASUREMENT

    _run(_flask("upgrade"), previous_database)

    assert _skinfolds_columns(url)["observacoes"] == ("text", "YES", None)
    assert _current_revision(url) == NOTES_REVISION
    assert _measurement_row(url) == {**MEASUREMENT, "observacoes": None}


def _only_skinfolds(item: Any, name: str | None, kind: str, reflected: bool, compare_to: Any) -> bool:
    """Tell Alembic to compare only the skinfolds table and what belongs to it.

    :param item: Table, column, index or constraint being compared.
    :param name: Name of the item.
    :param kind: Kind of the item, such as ``"table"`` or ``"column"``.
    :param reflected: Whether the item comes from the database.
    :param compare_to: The item it is compared to.
    :return: True when the item belongs to skinfolds.
    """
    table = item if kind == "table" else getattr(item, "table", None)
    return getattr(table, "name", name) == "skinfolds"


def _skinfolds_differences(url: URL) -> list[Any]:
    """Compare the models with the skinfolds table of the database, using Alembic's own comparison.

    :param url: URL of the database.
    :return: The differences Alembic finds, empty when the table matches the models.
    """
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": True, "include_object": _only_skinfolds},
            )
            return compare_metadata(context, db.metadata)
    finally:
        engine.dispose()


def test_models_and_the_migrated_database_agree_on_skinfolds(previous_database: PreviousDatabase) -> None:
    """Check that the models and the database differ in nothing on skinfolds once migrated, and in the column before.

    :param previous_database: Database with the schema of the previous revision.
    """
    before = _skinfolds_differences(previous_database.url)
    _run(_release_command(), previous_database)

    after = _skinfolds_differences(previous_database.url)

    assert [(kind, table, column.name) for kind, _, table, column in before] == [
        ("add_column", "skinfolds", "observacoes")
    ]
    assert after == []
