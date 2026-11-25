"""Restore the backup into a real PostgreSQL server and check that nothing was lost.

These tests never run by default. They need a PostgreSQL server (version 16, like the production one) in the
BACKUP_RESTORE_DATABASE_URL environment variable and the psql program, and they run with "pytest -m pg_restore".
Every test creates fresh databases with unique names and drops them at the end.
"""

import io
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL, make_url

from app.models import db
from app.services.backup import Snapshot, build_backup, quote_identifier, read_snapshot
from tests.constants import EMAILS

pytestmark = pytest.mark.pg_restore

ENV_VAR = "BACKUP_RESTORE_DATABASE_URL"
ENV_EXAMPLE = "postgresql://postgres:PASSWORD@127.0.0.1:55432/postgres"  # pragma: allowlist secret
RESTORE_TIMEOUT_SECONDS = 120
OTHER_REVISION = "000000000000"

DatabaseFactory = Callable[[str], URL]


@dataclass(frozen=True)
class BackupFiles:
    """A backup of the test database, unpacked and ready to be restored.

    :param sql_path: Path of the SQL script.
    :param manifest_counts: Row counts written in the manifest.
    :param manifest_revision: Alembic revision written in the manifest.
    :param source: What the source database held when the backup was made.
    :param guide_count_query: Query that the restore guide gives to count the rows of every table.
    """

    sql_path: Path
    manifest_counts: dict[str, int]
    manifest_revision: str | None
    source: Snapshot
    guide_count_query: str


def server_url() -> URL:
    """Read the URL of the PostgreSQL server and check that psql is available.

    The check runs inside the tests, not in a fixture, so a missing setting is reported as a failed test.

    :raises pytest.fail.Exception: If the environment variable or psql is missing; the tests never skip.
    :return: The URL of a database of the server, used to create the temporary databases.
    """
    value = os.environ.get(ENV_VAR)
    if not value:
        pytest.fail(
            f"{ENV_VAR} is not set. Point it to a PostgreSQL server, for example "
            f"{ENV_VAR}={ENV_EXAMPLE} (see tests/README.md).",
            pytrace=False,
        )
    if shutil.which("psql") is None:
        pytest.fail(
            "The psql program is not installed or not in the PATH, and the restore tests need it.", pytrace=False
        )
    return make_url(value).set(drivername="postgresql+psycopg2")


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
        name = f"emagreser_restore_{uuid.uuid4().hex[:10]}_{tag}"
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


@pytest.fixture
def backup_files(app: Flask, tricky_rows: dict[str, Any], alembic_table: str, tmp_path: Path) -> BackupFiles:
    """Make a backup of the test database, with the hostile rows and a known revision, and unpack its script.

    :param app: Flask application.
    :param tricky_rows: Temporary rows with hostile text, NULLs, odd numbers and secrets.
    :param alembic_table: Revision stored in the temporary Alembic table.
    :param tmp_path: Temporary folder of the test.
    :return: The unpacked backup and the snapshot of the source database.
    """
    with app.app_context():
        source = read_snapshot(db.engine)
        backup = build_backup(EMAILS["admin"])
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        (sql_name,) = [name for name in archive.namelist() if name.endswith(".sql")]
        (tmp_path / sql_name).write_bytes(archive.read(sql_name))
        manifest = json.loads(archive.read("manifest.json"))
        guide = archive.read("LEIA-ME.txt").decode("utf-8")
    assert manifest["alembic_revision"] == alembic_table
    query = re.search(r"^ {3}SELECT '.*?ORDER BY tabela;$", guide, re.DOTALL | re.MULTILINE)
    assert query is not None, "the restore guide has no count query"
    return BackupFiles(
        tmp_path / sql_name, manifest["row_counts"], manifest["alembic_revision"], source, query.group(0)
    )


def _engine(url: URL) -> Engine:
    """Create an engine for a restored database.

    :param url: URL of the database.
    :return: The engine.
    """
    return create_engine(url)


def _restore(url: URL, sql_path: Path) -> subprocess.CompletedProcess[str]:
    """Restore a script with psql, stopping at the first error, as the restore guide tells.

    :param url: URL of the target database.
    :param sql_path: Path of the SQL script.
    :return: The finished process, with its output as text.
    """
    command = [
        "psql",
        "-X",
        "-h",
        str(url.host),
        "-p",
        str(url.port or 5432),
        "-U",
        str(url.username),
        "-d",
        str(url.database),
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(sql_path),
    ]
    environment = {**os.environ, "PGPASSWORD": url.password or ""}
    return subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=RESTORE_TIMEOUT_SECONDS, check=False
    )


def _assert_restored(url: URL, files: BackupFiles) -> None:
    """Check that the restored database has the counts of the manifest and every row of the source.

    :param url: URL of the restored database.
    :param files: The backup that was restored.
    """
    engine = _engine(url)
    try:
        restored = read_snapshot(engine)
    finally:
        engine.dispose()

    assert restored.dialect == "postgresql"
    assert {data.table.name: len(data.rows) for data in restored.tables} == files.manifest_counts
    for original, copy in zip(files.source.tables, restored.tables):
        assert original.table.name == copy.table.name
        assert copy.rows == original.rows, f"the rows of {original.table.name} differ from the source"
    assert ", ".join(restored.revisions) == files.manifest_revision


def _assert_restore_worked(result: subprocess.CompletedProcess[str]) -> None:
    """Check that psql finished without any error.

    :param result: The finished psql process.
    """
    assert result.returncode == 0, result.stderr
    assert "ERROR" not in result.stderr, result.stderr


def test_restore_into_an_empty_database(new_database: DatabaseFactory, backup_files: BackupFiles) -> None:
    """Check that the script recreates everything in a brand new database, with the same counts and rows.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("empty")

    _assert_restore_worked(_restore(url, backup_files.sql_path))

    _assert_restored(url, backup_files)
    assert backup_files.manifest_counts["diets"] >= 7
    assert backup_files.manifest_revision is not None


def test_count_query_of_the_guide_matches_the_manifest(
    new_database: DatabaseFactory, backup_files: BackupFiles
) -> None:
    """Check that the query given in the restore guide runs as written and counts every table, "user" included.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("counts")
    _assert_restore_worked(_restore(url, backup_files.sql_path))
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            counted = dict(connection.exec_driver_sql(backup_files.guide_count_query).all())
            unquoted = connection.exec_driver_sql("SELECT COUNT(*) FROM user").scalar_one()
    finally:
        engine.dispose()

    assert counted == backup_files.manifest_counts
    assert backup_files.manifest_counts["user"] > 1
    assert unquoted == 1


def test_restore_into_a_database_whose_tables_already_exist_empty(
    new_database: DatabaseFactory, backup_files: BackupFiles
) -> None:
    """Check the restore into a database the application already started on, which created the empty tables.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("created")
    engine = _engine(url)
    try:
        db.metadata.create_all(engine)
    finally:
        engine.dispose()

    _assert_restore_worked(_restore(url, backup_files.sql_path))

    _assert_restored(url, backup_files)


def test_restore_replaces_the_revision_of_a_migrated_empty_database(
    new_database: DatabaseFactory, backup_files: BackupFiles
) -> None:
    """Check that an empty database that was migrated to another revision ends with the revision of the backup.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("migrated")
    engine = _engine(url)
    try:
        db.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            connection.exec_driver_sql(f"INSERT INTO alembic_version VALUES ('{OTHER_REVISION}')")
    finally:
        engine.dispose()

    _assert_restore_worked(_restore(url, backup_files.sql_path))

    _assert_restored(url, backup_files)


def test_new_rows_get_the_next_id(new_database: DatabaseFactory, backup_files: BackupFiles) -> None:
    """Check that, after the restore, new rows continue the numbering instead of colliding with restored ids.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("sequences")
    _assert_restore_worked(_restore(url, backup_files.sql_path))
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            diets = db.metadata.tables["diets"]
            highest = connection.execute(select(func.max(diets.c.id))).scalar_one()
            new_id = connection.execute(
                text("INSERT INTO diets (name, description) VALUES ('Nova dieta', 'x') RETURNING id")
            ).scalar_one()
            assert new_id == highest + 1
            serial_tables = [table for table in db.metadata.sorted_tables if table.autoincrement_column is not None]
            assert len(serial_tables) == 8
            for table in serial_tables:
                column = table.autoincrement_column
                top = connection.execute(select(func.max(table.c[column.name]))).scalar_one()
                following = connection.execute(
                    text("SELECT nextval(pg_get_serial_sequence(:table, :column))"),
                    {"table": quote_identifier(table.name), "column": column.name},
                ).scalar_one()
                assert following == (top or 0) + 1, table.name
    finally:
        engine.dispose()


def test_restoring_twice_fails_and_changes_nothing(new_database: DatabaseFactory, backup_files: BackupFiles) -> None:
    """Check that restoring the same file into a database that is already filled stops with an error.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("twice")
    _assert_restore_worked(_restore(url, backup_files.sql_path))
    engine = _engine(url)
    try:
        before = read_snapshot(engine)
        second = _restore(url, backup_files.sql_path)
        after = read_snapshot(engine)
    finally:
        engine.dispose()

    assert second.returncode != 0
    assert "não está vazio" in second.stderr
    assert [data.rows for data in after.tables] == [data.rows for data in before.tables]
    assert after.revisions == before.revisions
    _assert_restored(url, backup_files)


def test_restore_into_a_database_with_other_data_fails_and_rolls_back(
    new_database: DatabaseFactory, backup_files: BackupFiles
) -> None:
    """Check that one row of other data is enough to stop the restore, and that nothing of the backup gets in.

    :param new_database: Function that creates empty databases.
    :param backup_files: The backup to restore.
    """
    url = new_database("other")
    engine = _engine(url)
    try:
        db.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO diets (id, name, description) VALUES (9000, 'Outra', 'x')"))
        result = _restore(url, backup_files.sql_path)
        restored = read_snapshot(engine)
    finally:
        engine.dispose()

    assert result.returncode != 0
    assert "não está vazio" in result.stderr
    counts = {data.table.name: len(data.rows) for data in restored.tables}
    assert counts["diets"] == 1
    assert sum(counts.values()) == 1
    assert restored.revisions == ()
