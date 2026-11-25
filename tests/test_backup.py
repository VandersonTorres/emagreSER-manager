"""Tests of the database backup: the archive contents, the superuser access, the menu entry and the audit log."""

import builtins
import csv
import io
import json
import logging
import re
import tempfile
import time
import zipfile
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as day_time
from datetime import timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from bs4 import BeautifulSoup
from flask import Flask
from flask.testing import FlaskClient
from flask_login import AnonymousUserMixin
from sqlalchemy import Column, Index, Integer, LargeBinary, MetaData, String, Table, create_engine, event, func, select
from werkzeug.test import TestResponse

from app.models import Patients, SkinFolds, User, db
from app.navigation import NAV_ITEMS, build_navigation, visible_items
from app.services.backup import (
    CSV_RENDERERS,
    SAO_PAULO,
    SECRET_COLUMNS,
    SQL_RENDERERS,
    BackupArchive,
    Kind,
    Snapshot,
    TableData,
    build_backup,
    column_kind,
    iter_sql_script,
    read_snapshot,
)
from app.superusers import is_superuser, superuser_emails
from tests.aliases import ClientFactory
from tests.constants import EMAILS, FORMULAS, RECOVERY_CODES, SECRETS, TRICKY_TEXT

NOW = datetime(2026, 11, 23, 10, 15, 30, tzinfo=SAO_PAULO)
SQL_NAME = "emagreser-2026-11-23_1015.sql"
ZIP_NAME = "emagreser-backup-2026-11-23_1015.zip"
BACKUP_URL = "/admin/backup"
DOWNLOAD_NAME = re.compile(r'attachment; filename="?emagreser-backup-\d{4}-\d{2}-\d{2}_\d{4}\.zip"?')
SECRET_VALUES = [*SECRETS.values(), *RECOVERY_CODES]


def _table_names() -> list[str]:
    """List the names of every table of the models.

    :return: The table names, in dependency order.
    """
    return [table.name for table in db.metadata.sorted_tables]


def _read_zip(content: bytes) -> zipfile.ZipFile:
    """Open the bytes of a backup as a ZIP archive.

    :param content: Bytes of the archive.
    :return: The archive.
    """
    return zipfile.ZipFile(io.BytesIO(content))


def _sql(archive: zipfile.ZipFile) -> str:
    """Read the SQL script of a backup archive.

    :param archive: The backup archive.
    :return: The text of the only ``.sql`` member.
    """
    names = [name for name in archive.namelist() if name.endswith(".sql")]
    assert len(names) == 1
    return archive.read(names[0]).decode("utf-8")


def _csv_rows(archive: zipfile.ZipFile, table: str) -> list[dict[str, str]]:
    """Parse the spreadsheet of a table.

    :param archive: The backup archive.
    :param table: Name of the table.
    :return: One dict per row, keyed by column name.
    """
    text_content = archive.read(f"csv/{table}.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text_content, newline=""), delimiter=";"))


def _build(app: Flask, who: str = EMAILS["admin"], now: datetime = NOW) -> BackupArchive:
    """Build a backup of the test database.

    :param app: Flask application.
    :param who: E-mail of the user who asks for the backup.
    :param now: Generation time.
    :return: The generated backup.
    """
    with app.app_context():
        return build_backup(who, now=now)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", set()),
        ("  \n ", set()),
        (None, set()),
        ("a@x.com", {"a@x.com"}),
        (" A@X.com ", {"a@x.com"}),
        ("a@x.com,b@y.com", {"a@x.com", "b@y.com"}),
        ("a@x.com; b@y.com  c@z.com\nd@w.com", {"a@x.com", "b@y.com", "c@z.com", "d@w.com"}),
        (",;a@x.com;,", {"a@x.com"}),
    ],
)
def test_superuser_emails_are_parsed_from_the_config(
    app: Flask, set_superusers: Callable[[str], None], value: str | None, expected: set[str]
) -> None:
    """Check that the setting accepts commas, semicolons and whitespace, trims, lower-cases and tolerates emptiness.

    :param app: Flask application.
    :param set_superusers: Function that sets the superuser e-mails.
    :param value: Value of the setting.
    :param expected: E-mails that must come out of the parser.
    """
    set_superusers(value)
    with app.app_context():
        assert superuser_emails() == expected


def test_superusers_are_empty_by_default(app: Flask) -> None:
    """Check that, without any configuration, nobody is a superuser.

    :param app: Flask application.
    """
    with app.app_context():
        assert superuser_emails() == frozenset()
        assert not is_superuser(SimpleNamespace(is_authenticated=True, email=EMAILS["admin"]))


def test_is_superuser_matches_authenticated_users_only(app: Flask, set_superusers: Callable[[str], None]) -> None:
    """Check that the e-mail match ignores case and spaces and that an anonymous visitor is never a superuser.

    :param app: Flask application.
    :param set_superusers: Function that sets the superuser e-mails.
    """
    set_superusers("Boss@Test.Local")
    with app.app_context():
        assert is_superuser(SimpleNamespace(is_authenticated=True, email=" boss@test.local "))
        assert not is_superuser(SimpleNamespace(is_authenticated=True, email="other@test.local"))
        assert not is_superuser(SimpleNamespace(is_authenticated=True, email=None))
        assert not is_superuser(AnonymousUserMixin())


def test_menu_entry_is_declared_for_superusers_only() -> None:
    """Check that the Backup entry is the last one and shows up only when the user is a superuser."""
    assert NAV_ITEMS[-1].label == "Backup"
    assert NAV_ITEMS[-1].superuser_only
    for roles in (["admin"], ["secretary"], ["nutritionist"], ["admin", "secretary", "nutritionist"], []):
        assert "Backup" not in [item.label for item in visible_items(roles)]
        assert [item.label for item in visible_items(roles, superuser=True)][-1] == "Backup"


def test_navigation_links_the_backup_page_for_superusers(app: Flask) -> None:
    """Check the link, the icon and the active state of the Backup entry.

    :param app: Flask application.
    """
    with app.test_request_context():
        links = build_navigation(["nutritionist"], "backup.show_backup", superuser=True)
        plain = build_navigation(["nutritionist"], "backup.show_backup")

    backup = links[-1]
    assert (backup.label, backup.url, backup.icon, backup.active) == ("Backup", BACKUP_URL, "database-down", True)
    assert "Backup" not in [link.label for link in plain]


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_menu_shows_backup_only_to_listed_users(
    client_for: ClientFactory, set_superusers: Callable[[str], None], role: str
) -> None:
    """Check that the sidebar lists Backup to the listed e-mail only, whatever the role, and marks it when open.

    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    :param role: Role of the user under test.
    """
    other = "admin" if role != "admin" else "secretary"

    def sidebar(client: FlaskClient, path: str = "/") -> list[str]:
        """List the labels of the sidebar entries of a page.

        :param client: Test client.
        :param path: Page to open.
        :return: The text of every sidebar link.
        """
        soup = BeautifulSoup(client.get(path).get_data(as_text=True), "html.parser")
        return [link.get_text().strip() for link in soup.select("#app-sidebar nav a")]

    assert "Backup" not in sidebar(client_for(role))

    set_superusers(EMAILS[role])

    assert sidebar(client_for(role))[-1] == "Backup"
    assert "Backup" not in sidebar(client_for(other))
    soup = BeautifulSoup(client_for(role).get(BACKUP_URL).get_data(as_text=True), "html.parser")
    assert [link.get_text().strip() for link in soup.select("#app-sidebar a[aria-current='page']")] == ["Backup"]


def test_archive_members_and_names(app: Flask) -> None:
    """Check the archive and download names, and that every expected member is in the ZIP.

    :param app: Flask application.
    """
    backup = _build(app)

    with _read_zip(backup.content) as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == sorted(
            ["LEIA-ME.txt", "manifest.json", SQL_NAME, *[f"csv/{name}.csv" for name in _table_names()]]
        )
        assert {info.compress_type for info in archive.infolist()} == {zipfile.ZIP_DEFLATED}
    assert backup.filename == ZIP_NAME


def test_names_use_the_sao_paulo_time(app: Flask) -> None:
    """Check that a time given in UTC is converted to Brasília time in the names and in the manifest.

    :param app: Flask application.
    """
    backup = _build(app, now=datetime(2026, 11, 23, 13, 15, 30, tzinfo=timezone.utc))

    with _read_zip(backup.content) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert backup.filename == ZIP_NAME
    assert manifest["generated_at"] == "2026-11-23T10:15:30-03:00"


def test_manifest_counts_match_the_database(app: Flask, seed: dict[str, Any], tricky_rows: dict[str, Any]) -> None:
    """Check the manifest fields and that every row count equals the count of the table in the database.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param tricky_rows: Temporary rows added to the database.
    """
    backup = _build(app, who="quem.gerou@test.local")

    with _read_zip(backup.content) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    with app.app_context():
        counts = {
            table.name: db.session.execute(select(func.count()).select_from(table)).scalar_one()
            for table in db.metadata.sorted_tables
        }
    assert manifest["row_counts"] == counts == backup.row_counts
    assert counts["user"] >= 4 and counts["diets"] >= 3 and counts["patients"] >= 4
    assert manifest["format_version"] == 1
    assert manifest["generated_by"] == "quem.gerou@test.local"
    assert manifest["generated_at"] == "2026-11-23T10:15:30-03:00"
    assert manifest["database_dialect"] == "sqlite"
    assert manifest["alembic_revision"] is None
    assert manifest["sql_file"] == SQL_NAME


def test_known_alembic_revision_goes_to_the_manifest_and_the_script(app: Flask, alembic_table: str) -> None:
    """Check that the revision stored in the database is reported and restored.

    :param app: Flask application.
    :param alembic_table: Revision stored in the temporary Alembic table.
    """
    with _read_zip(_build(app).content) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        script = _sql(archive)

    assert manifest["alembic_revision"] == alembic_table
    assert f"INSERT INTO alembic_version (version_num) VALUES ('{alembic_table}');" in script
    assert script.index("DELETE FROM alembic_version;") < script.index("INSERT INTO alembic_version")


def test_unknown_alembic_revision_writes_no_row(app: Flask) -> None:
    """Check that the Alembic table is still created, but left empty, when the database has no revision.

    :param app: Flask application.
    """
    with _read_zip(_build(app).content) as archive:
        script = _sql(archive)

    assert "CREATE TABLE IF NOT EXISTS alembic_version (" in script
    assert "version_num VARCHAR(32) NOT NULL" in script
    assert "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)" in script
    assert "INSERT INTO alembic_version" not in script
    assert "DELETE FROM alembic_version" not in script


def test_every_table_has_a_spreadsheet_for_excel(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check the byte order mark, the delimiter, the header and the Portuguese formats of the spreadsheets.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with _read_zip(_build(app).content) as archive:
        for table in db.metadata.sorted_tables:
            raw = archive.read(f"csv/{table.name}.csv")
            secret = SECRET_COLUMNS.get(table.name, frozenset())
            expected = ";".join(column.name for column in table.columns if column.name not in secret)
            assert raw.startswith(b"\xef\xbb\xbf"), table.name
            assert raw.decode("utf-8-sig").split("\r\n", 1)[0] == expected, table.name
        patients = [row for row in _csv_rows(archive, "patients") if row["name"] == TRICKY_TEXT]
        users = _csv_rows(archive, "user")
        raw_patients = archive.read("csv/patients.csv").decode("utf-8-sig")

    assert raw_patients.split("\r\n", 1)[0].startswith("id;name;gender;birth_date;")
    (patient,) = patients
    assert patient["water"] == "72,5"
    assert patient["intestine"] == "3"
    assert patient["birth_date"] == "1985-03-09"
    assert patient["started_at"] == "2025-01-02 03:04:05"
    assert patient["hours"] == "07:30:05"
    assert patient["objective"] == "'=Objetivo"
    assert patient["cpf"] == ""
    assert patient["specialist_id"] == ""
    assert patient["email"] == ""
    assert {row["active"] for row in users} == {"sim"}


def test_spreadsheet_writes_false_as_no(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check that a false boolean is written as "não" in the spreadsheet.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with app.app_context():
        db.session.execute(User.__table__.update().where(User.id == tricky_rows["user"]).values(active=False))
        db.session.commit()

    with _read_zip(_build(app).content) as archive:
        rows = {row["email"]: row for row in _csv_rows(archive, "user")}

    assert rows["segredos@test.local"]["active"] == "não"


def test_number_renderers() -> None:
    """Check the numbers of the spreadsheet (decimal comma, no exponent) and of the SQL (exact round trip)."""
    csv_number, sql_number = CSV_RENDERERS[Kind.NUMBER], SQL_RENDERERS[Kind.NUMBER]

    assert [csv_number(value) for value in (72.5, 2.0, -0.25, 1e-05, 1.5e20, 3)] == [
        "72,5",
        "2,0",
        "-0,25",
        "0,00001",
        "150000000000000000000",
        "3",
    ]
    assert [sql_number(value) for value in (72.5, 0.1, 1e-05, 1.5e20, -0.0, 3)] == [
        "72.5",
        "0.1",
        "1e-05",
        "1.5e+20",
        "-0.0",
        "3",
    ]
    assert sql_number(float("nan")) == "'NaN'"
    assert sql_number(float("inf")) == "'Infinity'"
    assert sql_number(float("-inf")) == "'-Infinity'"
    for value in (0.1, 1 / 3, 1e-300, 123456789.123456789, 2.0**70):
        assert float(sql_number(value)) == value


def test_date_and_text_renderers() -> None:
    """Check the literals of the SQL script for booleans, dates, times and texts."""
    assert SQL_RENDERERS[Kind.BOOLEAN](True) == "true"
    assert SQL_RENDERERS[Kind.BOOLEAN](False) == "false"
    assert SQL_RENDERERS[Kind.INTEGER](7) == "7"
    assert SQL_RENDERERS[Kind.DATE](date(2026, 1, 2)) == "'2026-01-02'"
    assert SQL_RENDERERS[Kind.TIME](day_time(7, 30, 5)) == "'07:30:05'"
    assert SQL_RENDERERS[Kind.DATETIME](datetime(2026, 1, 2, 3, 4, 5)) == "'2026-01-02 03:04:05'"
    assert SQL_RENDERERS[Kind.DATETIME](datetime(2026, 1, 2, 3, 4, 5, 6)) == "'2026-01-02 03:04:05.000006'"
    assert SQL_RENDERERS[Kind.TEXT]("D'Avila") == "'D''Avila'"
    assert SQL_RENDERERS[Kind.TEXT]("a\\b") == "'a\\b'"
    assert CSV_RENDERERS[Kind.DATETIME](datetime(2026, 1, 2, 3, 4, 5, 6)) == "2026-01-02 03:04:05"
    assert CSV_RENDERERS[Kind.TIME](day_time(7, 30, 5, 9)) == "07:30:05"


def test_unsupported_column_type_is_rejected() -> None:
    """Check that a column type the backup cannot write fails loudly instead of producing a wrong backup."""
    table = Table("blobs", MetaData(), Column("data", LargeBinary))

    with pytest.raises(TypeError, match="blobs.data"):
        column_kind(table.c.data)


def test_every_model_column_has_a_supported_type() -> None:
    """Check that every column of every model is classified, so a new model never breaks the backup."""
    for table in db.metadata.sorted_tables:
        for column in table.columns:
            assert isinstance(column_kind(column), Kind), (table.name, column.name)


def test_secret_columns_exist_in_the_models() -> None:
    """Check that every column named as secret exists, so a rename of a model column cannot leak it silently."""
    for table_name, names in SECRET_COLUMNS.items():
        assert names <= {column.name for column in db.metadata.tables[table_name].columns}


def test_secrets_stay_out_of_every_spreadsheet_but_are_in_the_script(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check that no secret column or value is in any spreadsheet and that the script keeps them for the restore.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with app.app_context():
        hashes = [row.password for row in User.query.all() if row.password]
        uniquifiers = [row.fs_uniquifier for row in User.query.all()]
    assert len(hashes) >= 4 and len(uniquifiers) >= 4

    with _read_zip(_build(app).content) as archive:
        script = _sql(archive)
        spreadsheets = {
            name: archive.read(name).decode("utf-8-sig") for name in archive.namelist() if name.endswith(".csv")
        }
        header = spreadsheets["csv/user.csv"].split("\r\n", 1)[0].split(";")

    assert not set(SECRET_COLUMNS["user"]) & set(header)
    assert "email" in header and "username" in header
    for name, content in spreadsheets.items():
        for secret in [*SECRET_VALUES, *hashes, *uniquifiers]:
            assert secret not in content, (name, "a secret value is in the spreadsheet")
    for secret in [*SECRETS.values(), *hashes, *uniquifiers, ",".join(RECOVERY_CODES)]:
        assert secret in script


def test_spreadsheet_protects_against_formula_injection(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check that texts that start like a formula get a leading apostrophe and other texts stay as they are.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with _read_zip(_build(app).content) as archive:
        rows = {int(row["id"]): row for row in _csv_rows(archive, "diets")}

    protected = [rows[diet_id] for diet_id in tricky_rows["diets"][1:]]
    assert [row["description"] for row in protected] == [f"'{prefix}" for prefix in FORMULAS]
    assert [row["name"] for row in protected] == [f"'{prefix}fórmula" for prefix in FORMULAS]
    assert rows[tricky_rows["diets"][0]]["name"] == TRICKY_TEXT
    assert rows[tricky_rows["diets"][0]]["diet_file"] == ""


def test_script_structure(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check the header, the transaction, the tables, the quoting of reserved words and the sequences of the script.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with _read_zip(_build(app).content) as archive:
        script = _sql(archive)

    lines = script.splitlines()
    assert lines[0].startswith("--")
    assert "2026-11-23T10:15:30-03:00" in script.split("SET client_encoding")[0]
    assert f'psql "URL_DO_BANCO" -v ON_ERROR_STOP=1 -f {SQL_NAME}' in lines[2]
    assert script.index("SET client_encoding = 'UTF8';") < script.index("SET standard_conforming_strings = on;")
    assert script.index("SET standard_conforming_strings = on;") < script.index("\nBEGIN;\n")
    assert script.rstrip().endswith("COMMIT;")
    assert script.count("\nBEGIN;\n") == 1 and script.count("COMMIT;") == 1
    for name in _table_names():
        quoted = '"user"' if name == "user" else name
        assert f"CREATE TABLE IF NOT EXISTS {quoted} (" in script, name
    assert 'CREATE TABLE IF NOT EXISTS "user" (' in script
    assert 'INSERT INTO "user" (' in script
    assert '"order" INTEGER' in script
    assert re.search(r'INSERT INTO diets \(id, name, description, diet_file, temp_diet_file, "order"\)', script)
    assert 'REFERENCES "user" (id)' in script
    serial_tables = [t for t in db.metadata.sorted_tables if t.autoincrement_column is not None]
    assert script.count("pg_get_serial_sequence(") == len(serial_tables) == 8
    assert (
        "SELECT setval(pg_get_serial_sequence('\"user\"', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL)"
        ' FROM "user";'
    ) in script
    assert script.index("INSERT INTO") < script.index("pg_get_serial_sequence(") < script.index("COMMIT;")
    assert script.index("CREATE TABLE IF NOT EXISTS skinfolds") < script.index("DO $$") < script.index("INSERT INTO")


def test_script_creates_the_indexes_of_the_models() -> None:
    """Check that the index of a model table is created with IF NOT EXISTS and that a table without keys is accepted."""
    table = Table("notes", MetaData(), Column("id", Integer, primary_key=True), Column("title", String(20)))
    Index("ix_notes_title", table.c.title)
    snapshot = Snapshot([TableData(table, [(1, "a"), (2, None)])], (), "sqlite")

    script = "".join(iter_sql_script(snapshot, NOW, SQL_NAME))

    assert "CREATE TABLE IF NOT EXISTS notes (" in script
    assert "CREATE INDEX IF NOT EXISTS ix_notes_title ON notes (title);" in script
    assert "INSERT INTO notes (id, title) VALUES\n(1, 'a'),\n(2, NULL);" in script


def test_script_refuses_a_database_that_is_not_empty(app: Flask) -> None:
    """Check that the script starts with a guard that raises an error for every table that already has rows.

    :param app: Flask application.
    """
    with _read_zip(_build(app).content) as archive:
        script = _sql(archive)

    guard = script[script.index("DO $$") : script.index("$$;") + 3]
    for name in _table_names():
        quoted = '"user"' if name == "user" else name
        assert f"PERFORM 1 FROM {quoted} LIMIT 1;" in guard
    assert guard.count("RAISE EXCEPTION") == len(_table_names())
    assert "alembic_version" not in guard


def test_script_writes_tricky_text_safely(app: Flask, tricky_rows: dict[str, Any]) -> None:
    """Check that quotes, backslashes, newlines, semicolons, accents and emoji are written without being altered.

    :param app: Flask application.
    :param tricky_rows: Temporary rows added to the database.
    """
    with _read_zip(_build(app).content) as archive:
        script = _sql(archive)

    assert "'D''Avila \\ barra\nnova linha; ponto e vírgula, ção 😀 \"aspas\" -- :var \\q'" in script
    assert "'-1fórmula'" in script and "'=1+1fórmula'" in script
    assert "72.5" in script
    assert "'1985-03-09'" in script and "'07:30:05'" in script and "'2025-01-02 03:04:05.123456'" in script
    assert "NULL" in script


def test_script_keeps_null_lists_as_null(app: Flask) -> None:
    """Check that a NULL list column is read as NULL, not as an empty list, so the restore is exact.

    :param app: Flask application.
    """
    with app.app_context():
        snapshot = read_snapshot(db.engine)
        role = next(data for data in snapshot.tables if data.table.name == "role")
        position = [column.name for column in role.table.columns].index("permissions")

    assert role.rows and {row[position] for row in role.rows} == {None}


def test_tables_are_read_in_primary_key_order(app: Flask, seed: dict[str, Any]) -> None:
    """Check that rows come out ordered by primary key, and by every column when a table has no primary key.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.app_context():
        snapshot = read_snapshot(db.engine)

    for data in snapshot.tables:
        if data.table.primary_key.columns:
            position = [column.name for column in data.table.columns].index("id")
            ids = [row[position] for row in data.rows]
            assert ids == sorted(ids), data.table.name
        else:
            assert data.rows == sorted(data.rows), data.table.name


def test_readme_explains_the_restore(app: Flask) -> None:
    """Check that the guide is in Portuguese and covers the contents, the LGPD, the PDFs and the restore steps.

    :param app: Flask application.
    """
    with _read_zip(_build(app, who="quem.gerou@test.local").content) as archive:
        readme = archive.read("LEIA-ME.txt").decode("utf-8")

    for expected in (
        "23/11/2026 às 10:15",
        "quem.gerou@test.local",
        SQL_NAME,
        "manifest.json",
        "csv/",
        "LGPD",
        "dados pessoais e de saúde",
        "PDF das dietas",
        "PostgreSQL 16",
        "banco de dados VAZIO",
        "-v ON_ERROR_STOP=1 -f " + SQL_NAME,
        "FLASK_SECURITY_PASSWORD_SALT",
        "não altera nada",
        'FROM "user"',
        'SELECT COUNT(*) FROM "user";',
    ):
        assert expected in readme, expected
    for name in _table_names():
        assert f"SELECT '{name}' AS tabela, COUNT(*) AS registros FROM " in readme, name
    assert "FROM user\n" not in readme
    assert "FROM user;" not in readme
    assert "heroku" not in readme.lower()


def test_big_database_is_backed_up_quickly(tmp_path: Path) -> None:
    """Check that a database of 50,000 rows is read and packed in a few seconds, with a bound that suits slow CI.

    :param tmp_path: Temporary folder for the throwaway SQLite database.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'big.db'}")
    db.metadata.create_all(engine)
    base = datetime(2026, 1, 1, 8, 0, 0)
    patients = [
        {
            "id": number,
            "name": f"Paciente {number} D'Avila",
            "gender": "feminino",
            "birth_date": date(1990, 1, 1) + timedelta(days=number % 3000),
            "tel_number": "(31) 90000-0000",
            "medication": "não",
            "intestine": 7,
            "allergies": "não",
            "water": 2.0 + number / 1000,
            "heartburn": "não",
            "physical_activities": "não",
            "frequency": 0,
            "objective": "Objetivo; com ponto e vírgula",
        }
        for number in range(1, 10_001)
    ]
    schedules = [
        {
            "id": number,
            "patient_id": number % 10_000 + 1,
            "date_time": base + timedelta(minutes=number),
            "specialist": "Profissional",
            "status": "pendente",
        }
        for number in range(1, 20_001)
    ]
    skinfolds = [
        {
            "id": number,
            "patient_id": number % 10_000 + 1,
            "data_medicao": date(2026, 1, 1),
            "altura": 1.7,
            "peso": 70.0 + number / 100,
            "massa_muscular": 30.0,
            "gordura": 25.0,
            "abdominal": 80.0,
            "cintura": 75.0,
            "quadril": 95.0,
            "idade_metabolica": 33,
            "pa": "12/8",
        }
        for number in range(1, 20_001)
    ]
    with engine.begin() as connection:
        connection.execute(Patients.__table__.insert(), patients)
        connection.execute(db.metadata.tables["schedules"].insert(), schedules)
        connection.execute(SkinFolds.__table__.insert(), skinfolds)

    started = time.perf_counter()
    backup = build_backup("quem.gerou@test.local", engine=engine, now=NOW)
    elapsed = time.perf_counter() - started

    assert sum(backup.row_counts.values()) == 50_000
    assert elapsed < 15, f"a backup of 50,000 rows took {elapsed:.1f} s"
    with _read_zip(backup.content) as archive:
        assert _sql(archive).count("INSERT INTO") == 50 + 100 + 100


def _assert_access(response: TestResponse, status: int) -> None:
    """Check the status of a response and, for a refusal, that the custom access denied page was rendered.

    :param response: Response to check.
    :param status: Expected status code.
    """
    assert response.status_code == status
    if status == 403:
        assert "Acesso negado" in response.get_data(as_text=True)


def test_anonymous_visitors_are_sent_to_the_login_page(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that an anonymous visitor is redirected to the login page on GET and on POST, with no work done.

    :param client: Anonymous test client.
    :param monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr("app.views.backup.build_backup", _forbidden_build)

    for response in (client.get(BACKUP_URL), client.post(BACKUP_URL)):
        assert response.status_code == 302
        assert response.headers["Location"].startswith("/login")


def _forbidden_build(*args: object, **kwargs: object) -> None:
    """Fail the test when a backup is built.

    :param args: Positional arguments of ``build_backup``.
    :param kwargs: Keyword arguments of ``build_backup``.
    :raises AssertionError: Always.
    """
    raise AssertionError("no backup may be built for this request")


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
@pytest.mark.parametrize("configured", ["", "outra.pessoa@test.local"])
def test_users_not_in_the_list_get_forbidden(
    client_for: ClientFactory,
    set_superusers: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    configured: str,
) -> None:
    """Check that, whatever the role, a user outside the list gets 403 on GET and POST before any work is done.

    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    :param monkeypatch: Pytest monkeypatch fixture.
    :param role: Role of the user under test.
    :param configured: Value of ``SUPERUSER_EMAILS``.
    """
    set_superusers(configured)
    monkeypatch.setattr("app.views.backup.build_backup", _forbidden_build)
    client = client_for(role)

    _assert_access(client.get(BACKUP_URL), 403)
    _assert_access(client.post(BACKUP_URL), 403)


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_superusers_open_the_page(client_for: ClientFactory, set_superusers: Callable[[str], None], role: str) -> None:
    """Check that a listed user opens the page, whatever the role, and that the page has what the user needs to know.

    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    :param role: Role of the user under test.
    """
    set_superusers(f" {EMAILS[role].upper()} ; outra@test.local")

    response = client_for(role).get(BACKUP_URL)

    assert response.status_code == 200
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    assert soup.select_one("h1").get_text().strip() == "Backup do banco de dados"
    body = soup.get_text(" ", strip=True)
    for expected in ("LGPD", "PDF das dietas", "Excel", "restauração", "Baixar backup"):
        assert expected in body, expected
    form = soup.select_one("main form[method=post]")
    assert form["action"] == BACKUP_URL
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Baixar backup"
    assert form.select_one("button .bi-download") is not None


@pytest.mark.parametrize("role", ["admin", "secretary", "nutritionist"])
def test_superusers_download_the_archive(
    client_for: ClientFactory, set_superusers: Callable[[str], None], role: str
) -> None:
    """Check the answer of a download: the ZIP, the attachment name, no caching and the contents of the archive.

    :param client_for: Factory of test clients by role.
    :param set_superusers: Function that sets the superuser e-mails.
    :param role: Role of the user under test.
    """
    set_superusers(EMAILS[role])

    response = client_for(role).post(BACKUP_URL)

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert DOWNLOAD_NAME.fullmatch(response.headers["Content-Disposition"])
    assert response.headers["Cache-Control"] == "no-store"
    with _read_zip(response.data) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert "LEIA-ME.txt" in archive.namelist()
    assert manifest["generated_by"] == EMAILS[role]
    assert set(manifest["row_counts"]) == set(_table_names())


def test_download_leaves_an_audit_line(
    client_nutritionist: FlaskClient, set_superusers: Callable[[str], None], caplog: pytest.LogCaptureFixture
) -> None:
    """Check that a download logs, at WARNING level, who downloaded and when, and never the data.

    :param client_nutritionist: Test client logged in as nutritionist.
    :param set_superusers: Function that sets the superuser e-mails.
    :param caplog: Pytest log capture fixture.
    """
    set_superusers(EMAILS["nutritionist"])

    with caplog.at_level(logging.INFO):
        before = datetime.now(SAO_PAULO)
        response = client_nutritionist.post(BACKUP_URL)

    assert response.status_code == 200
    records = [record for record in caplog.records if "Database backup downloaded" in record.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert EMAILS["nutritionist"] in message
    logged = re.search(r"at (\S+) \(", message)
    assert logged is not None
    assert before - timedelta(seconds=5) <= datetime.fromisoformat(logged.group(1)) <= datetime.now(SAO_PAULO)
    assert "password" not in message.lower()


def test_a_failure_flashes_a_message_and_goes_back(
    client_nutritionist: FlaskClient,
    set_superusers: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Check that an unexpected error is logged, flashed in Portuguese and answered with a redirect, never a 500.

    :param client_nutritionist: Test client logged in as nutritionist.
    :param set_superusers: Function that sets the superuser e-mails.
    :param monkeypatch: Pytest monkeypatch fixture.
    :param caplog: Pytest log capture fixture.
    """
    set_superusers(EMAILS["nutritionist"])

    def broken(*args: object, **kwargs: object) -> BackupArchive:
        """Fail the way a broken database would.

        :param args: Positional arguments of ``build_backup``.
        :param kwargs: Keyword arguments of ``build_backup``.
        :raises RuntimeError: Always.
        """
        raise RuntimeError("database is down")

    monkeypatch.setattr("app.views.backup.build_backup", broken)

    response = client_nutritionist.post(BACKUP_URL)

    assert response.status_code == 302
    assert response.headers["Location"] == BACKUP_URL
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1 and errors[0].exc_info is not None
    assert not [record for record in caplog.records if "downloaded" in record.getMessage()]
    page = client_nutritionist.get(BACKUP_URL).get_data(as_text=True)
    assert "Não foi possível gerar o backup. Tente novamente." in page


def test_nothing_is_written_to_disk(
    app: Flask,
    client_nutritionist: FlaskClient,
    set_superusers: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that a download neither opens a file for writing nor leaves anything in the temporary folders.

    :param app: Flask application.
    :param client_nutritionist: Test client logged in as nutritionist.
    :param set_superusers: Function that sets the superuser e-mails.
    :param monkeypatch: Pytest monkeypatch fixture.
    """
    set_superusers(EMAILS["nutritionist"])
    folders = [Path(tempfile.gettempdir()), Path(app.config["TEMP_UPLOAD_FOLDER"])]

    def listing() -> list[tuple[str, int]]:
        """List every file under the temporary folders with its size.

        :return: The sorted paths and sizes.
        """
        return sorted((str(path), path.stat().st_size) for folder in folders for path in folder.rglob("*"))

    real_open = builtins.open

    def read_only_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        """Open a file, refusing any mode that writes.

        :param file: Path or descriptor to open.
        :param mode: Mode of the file.
        :param args: Other positional arguments of ``open``.
        :param kwargs: Other keyword arguments of ``open``.
        :raises AssertionError: If the mode can write.
        :return: The opened file.
        """
        assert not set(mode) & set("wax+"), f"a backup must not write to {file}"
        return real_open(file, mode, *args, **kwargs)

    before = listing()
    monkeypatch.setattr(builtins, "open", read_only_open)

    response = client_nutritionist.post(BACKUP_URL)
    monkeypatch.undo()

    assert response.status_code == 200 and response.mimetype == "application/zip"
    assert listing() == before


def test_the_database_is_only_read(app: Flask) -> None:
    """Check that building a backup sends no statement that changes the database.

    :param app: Flask application.
    """
    statements: list[str] = []

    def record(connection: Any, cursor: Any, statement: str, *rest: Any) -> None:
        """Remember a statement that is about to run.

        :param connection: Connection that runs the statement.
        :param cursor: Cursor of the statement.
        :param statement: SQL text.
        :param rest: Parameters, context and many-flag of the event.
        """
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", record)
        try:
            build_backup(EMAILS["admin"], now=NOW)
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

    assert any(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert not [stmt for stmt in statements if re.match(r"\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)", stmt, re.I)]
