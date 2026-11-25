"""On-demand backup of the whole database, built in memory as a ZIP archive.

The archive holds a PostgreSQL script that recreates the database in an empty one, one Excel-friendly CSV per table
(without the secret columns), a manifest with the row counts and a restore guide in Brazilian Portuguese. Nothing is
ever written to disk: every file is produced in memory and streamed into the archive.
"""

import csv
import enum
import io
import json
import math
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    Date,
    DateTime,
    Engine,
    Integer,
    Numeric,
    Select,
    String,
    Table,
    Time,
    TypeDecorator,
)
from sqlalchemy import column as column_clause
from sqlalchemy import inspect, select
from sqlalchemy import table as table_clause
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.type_api import TypeEngine

from app.models import db

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
FORMAT_VERSION = 1
INSERT_BATCH_SIZE = 200
ALEMBIC_TABLE = "alembic_version"
ALEMBIC_TABLE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {ALEMBIC_TABLE} (\n"
    "    version_num VARCHAR(32) NOT NULL,\n"
    "    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)\n"
    ");"
)
SECRET_COLUMNS: dict[str, frozenset[str]] = {
    "user": frozenset(
        {
            "password",
            "fs_uniquifier",
            "fs_webauthn_user_handle",
            "tf_totp_secret",
            "us_totp_secrets",
            "mf_recovery_codes",
        }
    )
}
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
RESTORE_URL_EXAMPLE = "postgresql://USUARIO:SENHA@SERVIDOR:5432/NOME_DO_BANCO"  # pragma: allowlist secret
CSV_DELIMITER = ";"
CSV_BOM = "\ufeff"

POSTGRESQL = postgresql.dialect()
quote_identifier = POSTGRESQL.identifier_preparer.quote

Renderer = Callable[[Any], str]


class Kind(enum.Enum):
    """Family of a column type, which decides how its values are written in the SQL script and in the CSV."""

    BOOLEAN = enum.auto()
    INTEGER = enum.auto()
    NUMBER = enum.auto()
    DATETIME = enum.auto()
    DATE = enum.auto()
    TIME = enum.auto()
    TEXT = enum.auto()


@dataclass(frozen=True)
class TableData:
    """Rows of one table, read in the snapshot.

    :param table: The SQLAlchemy table.
    :param rows: Every row, ordered by primary key, with the values in the order of ``table.columns``.
    """

    table: Table
    rows: list[tuple[Any, ...]]


@dataclass(frozen=True)
class Snapshot:
    """Consistent copy of the database contents.

    :param tables: Data of every table, in foreign key dependency order.
    :param revisions: Alembic revisions stored in the database; empty when the table does not exist or is empty.
    :param dialect: Name of the database dialect the data was read from.
    """

    tables: list[TableData]
    revisions: tuple[str, ...]
    dialect: str


@dataclass(frozen=True)
class BackupArchive:
    """A generated backup, ready to be sent to the user.

    :param filename: Name suggested for the ZIP download.
    :param content: Bytes of the ZIP archive.
    :param row_counts: Number of rows of every table.
    """

    filename: str
    content: bytes
    row_counts: dict[str, int]


def column_kind(column: Column) -> Kind:
    """Classify the type of a column, looking through type decorators to the type stored in the database.

    :param column: Model column.
    :raises TypeError: If the column type is not supported by the backup.
    :return: The kind of the column.
    """
    column_type = _stored_type(column)
    families: tuple[tuple[type[TypeEngine], Kind], ...] = (
        (Boolean, Kind.BOOLEAN),
        (Integer, Kind.INTEGER),
        (Numeric, Kind.NUMBER),
        (DateTime, Kind.DATETIME),
        (Date, Kind.DATE),
        (Time, Kind.TIME),
        (String, Kind.TEXT),
    )
    for family, kind in families:
        if isinstance(column_type, family):
            return kind
    raise TypeError(
        f"The backup does not support the type {column.type!r} of the column {column.table.name}.{column.name}"
    )


def _stored_type(column: Column) -> TypeEngine:
    """Get the type a column has in the database, looking through type decorators.

    :param column: Model column.
    :return: The decorated type for a decorator, the type of the column otherwise.
    """
    return column.type.impl_instance if isinstance(column.type, TypeDecorator) else column.type


def _select_statement(table: Table) -> Select:
    """Build the query that reads every model column of a table, ordered by primary key.

    The query is built on a lightweight copy of the table that has the stored types, so decorated columns come back
    exactly as saved (for example, a ``NULL`` list column is not turned into an empty list).

    :param table: The table to read.
    :return: The select statement; tables without primary key are ordered by all their columns.
    """
    raw = table_clause(table.name, *[column_clause(column.name, _stored_type(column)) for column in table.columns])
    order_by = [raw.c[column.name] for column in table.primary_key.columns or table.columns]
    return select(*raw.c).order_by(*order_by)


def _read_revisions(connection: Connection) -> tuple[str, ...]:
    """Read the Alembic revisions stored in the database.

    :param connection: Connection inside the snapshot transaction.
    :return: The revisions, or an empty tuple when the Alembic table does not exist.
    """
    if not inspect(connection).has_table(ALEMBIC_TABLE):
        return ()
    rows = connection.execute(text(f"SELECT version_num FROM {ALEMBIC_TABLE} ORDER BY version_num")).scalars()
    return tuple(rows)


def read_snapshot(engine: Engine) -> Snapshot:
    """Read every table in a single read-only transaction.

    On PostgreSQL the transaction is REPEATABLE READ, so all the tables come from the same point in time even while
    the system keeps being used.

    :param engine: Engine of the database to read.
    :return: The data of every table and the Alembic revisions.
    """
    with engine.connect() as connection, connection.begin():
        if engine.dialect.name == "postgresql":
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        tables = [
            TableData(table, [tuple(row) for row in connection.execute(_select_statement(table))])
            for table in db.metadata.sorted_tables
        ]
        return Snapshot(tables, _read_revisions(connection), engine.dialect.name)


def _nullable(renderer: Renderer, null: str) -> Renderer:
    """Wrap a value renderer so that ``None`` is written as a fixed text.

    :param renderer: Renderer of the non-null values.
    :param null: Text written for ``None``.
    :return: The wrapped renderer.
    """

    def render(value: Any) -> str:
        """Render one value.

        :param value: Value of the cell, possibly ``None``.
        :return: The text of the cell.
        """
        return null if value is None else renderer(value)

    return render


def quote_literal(value: str) -> str:
    """Quote a text as a PostgreSQL string literal.

    Only the single quote needs care: with ``standard_conforming_strings`` on, backslashes are plain characters.

    :param value: The text.
    :return: The quoted literal, with every single quote doubled.
    """
    return "'" + value.replace("'", "''") + "'"


def _integer(value: int) -> str:
    """Write an integer.

    :param value: The integer.
    :return: Its digits, with no separator.
    """
    return str(int(value))


def _sql_boolean(value: bool) -> str:
    """Write a boolean as a PostgreSQL literal.

    :param value: The boolean.
    :return: ``true`` or ``false``.
    """
    return "true" if value else "false"


def _sql_number(value: float | int | Decimal) -> str:
    """Write a number as a PostgreSQL literal that reads back to exactly the same value.

    :param value: The number.
    :return: The literal; ``NaN`` and the infinities are quoted.
    """
    if isinstance(value, (float, Decimal)):
        if math.isnan(value):
            return "'NaN'"
        if math.isinf(value):
            return "'Infinity'" if value > 0 else "'-Infinity'"
    return repr(value) if isinstance(value, float) else str(value)


def _sql_datetime(value: datetime) -> str:
    """Write a date and time as a quoted ISO literal.

    :param value: The date and time.
    :return: The literal, for example ``'2026-11-23 10:15:00'``.
    """
    return quote_literal(value.isoformat(" "))


def _sql_date(value: date) -> str:
    """Write a date as a quoted ISO literal.

    :param value: The date.
    :return: The literal, for example ``'2026-11-23'``.
    """
    return quote_literal(value.isoformat())


def _sql_time(value: time) -> str:
    """Write a time of the day as a quoted ISO literal.

    :param value: The time.
    :return: The literal, for example ``'10:15:00'``.
    """
    return quote_literal(value.isoformat())


def _sql_text(value: str) -> str:
    """Write a text as a PostgreSQL string literal.

    :param value: The text.
    :return: The quoted literal.
    """
    return quote_literal(str(value))


SQL_RENDERERS: dict[Kind, Renderer] = {
    Kind.BOOLEAN: _sql_boolean,
    Kind.INTEGER: _integer,
    Kind.NUMBER: _sql_number,
    Kind.DATETIME: _sql_datetime,
    Kind.DATE: _sql_date,
    Kind.TIME: _sql_time,
    Kind.TEXT: _sql_text,
}


def _csv_boolean(value: bool) -> str:
    """Write a boolean in Portuguese.

    :param value: The boolean.
    :return: ``sim`` or ``não``.
    """
    return "sim" if value else "não"


def _csv_number(value: float | int | Decimal) -> str:
    """Write a number with a decimal comma and no exponent, the way Excel in Portuguese reads it.

    :param value: The number.
    :return: The text, for example ``72,5``.
    """
    exact = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    return format(exact, "f").replace(".", ",")


def _csv_datetime(value: datetime) -> str:
    """Write a date and time without fractions of a second.

    :param value: The date and time.
    :return: The text, for example ``2026-11-23 10:15:00``.
    """
    return value.isoformat(" ", "seconds")


def _csv_date(value: date) -> str:
    """Write a date in ISO format.

    :param value: The date.
    :return: The text, for example ``2026-11-23``.
    """
    return value.isoformat()


def _csv_time(value: time) -> str:
    """Write a time of the day without fractions of a second.

    :param value: The time.
    :return: The text, for example ``10:15:00``.
    """
    return value.isoformat("seconds")


def _csv_text(value: str) -> str:
    """Write a text so that a spreadsheet never runs it as a formula.

    :param value: The text.
    :return: The text, with a leading apostrophe when it starts like a formula.
    """
    content = str(value)
    return "'" + content if content.startswith(FORMULA_PREFIXES) else content


CSV_RENDERERS: dict[Kind, Renderer] = {
    Kind.BOOLEAN: _csv_boolean,
    Kind.INTEGER: _integer,
    Kind.NUMBER: _csv_number,
    Kind.DATETIME: _csv_datetime,
    Kind.DATE: _csv_date,
    Kind.TIME: _csv_time,
    Kind.TEXT: _csv_text,
}


def _renderers(table: Table, catalog: dict[Kind, Renderer], null: str) -> list[Renderer]:
    """Build the value renderer of every column of a table, once, so no work is repeated per row.

    :param table: The table.
    :param catalog: Renderer of each column kind.
    :param null: Text written for ``None``.
    :return: One renderer per column, in column order.
    """
    return [_nullable(catalog[column_kind(column)], null) for column in table.columns]


def _create_statements(table: Table) -> list[str]:
    """Compile the creation of a table and of its indexes for PostgreSQL, tolerating existing ones.

    :param table: The table.
    :return: The ``CREATE TABLE IF NOT EXISTS`` statement followed by the ``CREATE INDEX IF NOT EXISTS`` ones.
    """
    statements = [str(CreateTable(table, if_not_exists=True).compile(dialect=POSTGRESQL)).strip() + ";"]
    for index in sorted(table.indexes, key=lambda item: item.name or ""):
        statements.append(str(CreateIndex(index, if_not_exists=True).compile(dialect=POSTGRESQL)).strip() + ";")
    return statements


def _emptiness_guard(tables: Sequence[Table]) -> str:
    """Build the block that stops the restore when any table already has rows.

    :param tables: Tables that are about to be filled.
    :return: A ``DO`` block that raises an error, which makes the restore stop and roll back.
    """
    checks = "".join(
        f"    PERFORM 1 FROM {quote_identifier(table.name)} LIMIT 1;\n"
        "    IF FOUND THEN\n"
        f"        RAISE EXCEPTION 'O banco de destino não está vazio: a tabela % já tem dados.', "
        f"{quote_literal(table.name)};\n"
        "    END IF;\n"
        for table in tables
    )
    return f"DO $$\nBEGIN\n{checks}END\n$$;"


def _insert_statements(data: TableData) -> Iterator[str]:
    """Render the multi-row ``INSERT`` statements of a table.

    :param data: Rows of the table.
    :return: The statements, each with at most ``INSERT_BATCH_SIZE`` rows; nothing for an empty table.
    """
    table = data.table
    renderers = _renderers(table, SQL_RENDERERS, "NULL")
    columns = ", ".join(quote_identifier(column.name) for column in table.columns)
    head = f"INSERT INTO {quote_identifier(table.name)} ({columns}) VALUES\n"
    for start in range(0, len(data.rows), INSERT_BATCH_SIZE):
        batch = data.rows[start : start + INSERT_BATCH_SIZE]
        values = ",\n".join(
            "(" + ", ".join([render(value) for render, value in zip(renderers, row)]) + ")" for row in batch
        )
        yield f"{head}{values};"


def _sequence_statement(table: Table) -> str | None:
    """Build the statement that moves the id sequence of a table past its highest id.

    :param table: The table.
    :return: The ``setval`` statement, or ``None`` when the table has no auto-incremented primary key.
    """
    column = table.autoincrement_column
    if column is None:
        return None
    name, target = quote_identifier(column.name), quote_identifier(table.name)
    sequence = f"pg_get_serial_sequence({quote_literal(target)}, {quote_literal(column.name)})"
    return f"SELECT setval({sequence}, COALESCE(MAX({name}), 1), MAX({name}) IS NOT NULL) FROM {target};"


def iter_sql_script(snapshot: Snapshot, moment: datetime, sql_name: str) -> Iterator[str]:
    """Generate the PostgreSQL script that recreates the database in an empty one.

    :param snapshot: Data read from the database.
    :param moment: Generation time.
    :param sql_name: File name of the script, quoted in the restore command of the header.
    :return: The script, in chunks of whole statements.
    """
    tables = [data.table for data in snapshot.tables]
    generated_at = moment.isoformat(timespec="seconds")
    yield (
        "-- Backup do banco de dados do EmagreSER\n"
        f"-- Gerado em: {generated_at}\n"
        f'-- Para restaurar em um banco VAZIO: psql "URL_DO_BANCO" -v ON_ERROR_STOP=1 -f {sql_name}\n\n'
        "SET client_encoding = 'UTF8';\n"
        "SET standard_conforming_strings = on;\n"
        "BEGIN;\n\n"
    )
    for table in tables:
        yield "\n".join(_create_statements(table)) + "\n"
    yield f"{ALEMBIC_TABLE_DDL}\n\n{_emptiness_guard(tables)}\n\n"
    for data in snapshot.tables:
        for statement in _insert_statements(data):
            yield statement + "\n"
    if snapshot.revisions:
        values = ", ".join(f"({quote_literal(revision)})" for revision in snapshot.revisions)
        yield f"DELETE FROM {ALEMBIC_TABLE};\nINSERT INTO {ALEMBIC_TABLE} (version_num) VALUES {values};\n"
    for table in tables:
        statement = _sequence_statement(table)
        if statement:
            yield statement + "\n"
    yield "COMMIT;\n"


def csv_columns(table: Table) -> list[int]:
    """Pick the columns of a table that go into its spreadsheet, leaving out the secret ones.

    :param table: The table.
    :return: Positions, in column order, of the columns to export.
    """
    secret = SECRET_COLUMNS.get(table.name, frozenset())
    return [position for position, column in enumerate(table.columns) if column.name not in secret]


def render_csv(data: TableData) -> bytes:
    """Render a table as a CSV that Excel in Portuguese opens directly.

    :param data: Rows of the table.
    :return: UTF-8 bytes with a byte order mark, ``;`` as delimiter and one header line.
    """
    positions = csv_columns(data.table)
    columns = data.table.columns
    renderers = [_nullable(CSV_RENDERERS[column_kind(columns[position])], "") for position in positions]
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow([columns[position].name for position in positions])
    for row in data.rows:
        writer.writerow([render(row[position]) for render, position in zip(renderers, positions)])
    return (CSV_BOM + buffer.getvalue()).encode("utf-8")


def render_manifest(snapshot: Snapshot, moment: datetime, generated_by: str, sql_name: str) -> str:
    """Render the manifest that summarizes the backup.

    :param snapshot: Data read from the database.
    :param moment: Generation time.
    :param generated_by: E-mail of the user who generated the backup.
    :param sql_name: File name of the SQL script.
    :return: The manifest as indented JSON.
    """
    manifest = {
        "format_version": FORMAT_VERSION,
        "generated_at": moment.isoformat(timespec="seconds"),
        "generated_by": generated_by,
        "database_dialect": snapshot.dialect,
        "alembic_revision": ", ".join(snapshot.revisions) or None,
        "sql_file": sql_name,
        "row_counts": {data.table.name: len(data.rows) for data in snapshot.tables},
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def render_count_query() -> str:
    """Render one query that lists the row count of every table, for the reader to check a restore.

    The names are quoted, so the reserved word "user" counts the table and not the current_user function.

    :return: The SQL text, indented to sit inside the restore guide.
    """
    selects = [
        f"SELECT '{table.name}' AS tabela, COUNT(*) AS registros FROM {quote_identifier(table.name)}"
        for table in db.metadata.sorted_tables
    ]
    lines = [*"\nUNION ALL\n".join(selects).splitlines(), "ORDER BY tabela;"]
    return "\n".join(f"   {line}" for line in lines)


def render_readme(moment: datetime, generated_by: str, sql_name: str) -> str:
    """Render the guide, in Brazilian Portuguese, that explains the files and how to restore them.

    :param moment: Generation time.
    :param generated_by: E-mail of the user who generated the backup.
    :param sql_name: File name of the SQL script.
    :return: The text of the guide.
    """
    return f"""EmagreSER - Backup do banco de dados
====================================

Gerado em: {moment:%d/%m/%Y às %H:%M} (horário de Brasília)
Gerado por: {generated_by}

O QUE TEM NESTA PASTA
---------------------
- {sql_name}
  Cópia completa do banco de dados. É o arquivo usado para restaurar o sistema.
- csv/
  Uma planilha por tabela, para abrir no Excel. Não têm senhas nem códigos de acesso.
  Datas e horas aparecem como estão gravadas no sistema, sem conversão de fuso horário.
- manifest.json
  Resumo do backup: data, quem gerou e quantos registros há em cada tabela.
- LEIA-ME.txt
  Este guia.

O QUE NÃO ESTÁ INCLUÍDO
-----------------------
Os arquivos PDF das dietas não fazem parte do backup. O banco guarda apenas os links deles.

CUIDADO COM OS DADOS
--------------------
Estes arquivos têm dados pessoais e de saúde de pacientes, protegidos pela LGPD (Lei nº 13.709/2018).
O arquivo .sql também guarda as senhas (criptografadas) e os códigos de acesso dos usuários.
Guarde tudo em um lugar seguro, não compartilhe, não envie por e-mail ou aplicativo de mensagens e apague as
cópias que não forem mais necessárias.

COMO RESTAURAR
--------------
1. Instale o PostgreSQL 16 ou mais novo (e o programa psql, que vem com ele).
2. Crie um banco de dados VAZIO.
3. Rode o comando abaixo, trocando a URL pela do banco vazio:

   psql "{RESTORE_URL_EXAMPLE}" -v ON_ERROR_STOP=1 -f {sql_name}

4. Confira se a quantidade de registros de cada tabela é a mesma do manifest.json.
   Conecte no banco restaurado (psql "URL") e rode a consulta abaixo, que lista todas as tabelas:

{render_count_query()}

   Se for contar uma tabela por conta própria, escreva "user" entre aspas duplas (SELECT COUNT(*) FROM "user";).
   Sem as aspas, o PostgreSQL responde 1, que é o usuário atual e não a quantidade de registros.
5. O sistema que usar o banco restaurado precisa ter o mesmo valor de FLASK_SECURITY_PASSWORD_SALT do sistema
   original. Sem isso, ninguém consegue entrar.

Se o banco não estiver vazio, a restauração para com um erro e não altera nada.
"""


def _member(name: str, moment: datetime) -> zipfile.ZipInfo:
    """Describe a compressed archive member stamped with the generation time.

    :param name: Path of the member inside the archive.
    :param moment: Generation time.
    :return: The member description.
    """
    info = zipfile.ZipInfo(name, date_time=moment.timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def build_backup(generated_by: str, engine: Engine | None = None, now: datetime | None = None) -> BackupArchive:
    """Build the backup ZIP of the whole database in memory.

    :param generated_by: E-mail of the user who asked for the backup.
    :param engine: Engine of the database to read; defaults to the one of the current application.
    :param now: Generation time as an aware datetime; defaults to the current time.
    :return: The ZIP bytes with the download name and the row count of every table.
    """
    moment = (now or datetime.now(SAO_PAULO)).astimezone(SAO_PAULO)
    snapshot = read_snapshot(engine or db.engine)
    stamp = f"{moment:%Y-%m-%d_%H%M}"
    sql_name = f"emagreser-{stamp}.sql"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_member("LEIA-ME.txt", moment), render_readme(moment, generated_by, sql_name).encode("utf-8"))
        archive.writestr(
            _member("manifest.json", moment), render_manifest(snapshot, moment, generated_by, sql_name).encode("utf-8")
        )
        with archive.open(_member(sql_name, moment), "w") as sql_file:
            for chunk in iter_sql_script(snapshot, moment, sql_name):
                sql_file.write(chunk.encode("utf-8"))
        for data in snapshot.tables:
            archive.writestr(_member(f"csv/{data.table.name}.csv", moment), render_csv(data))

    row_counts = {data.table.name: len(data.rows) for data in snapshot.tables}
    return BackupArchive(f"emagreser-backup-{stamp}.zip", buffer.getvalue(), row_counts)
