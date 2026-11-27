"""Alembic scripts: a single head, the revision that adds the observation of a measurement, and the release command."""

import ast
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import Script, ScriptDirectory

from app.models import SkinFolds

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
PROCFILE = ROOT / "Procfile"
PREVIOUS_REVISION = "fb739ba57804"  # pragma: allowlist secret
NOTES_REVISION = "03f89a0c5fa6"  # pragma: allowlist secret
RELEASE_LINE = "release: flask --app run db upgrade"
WEB_LINE = "web: gunicorn run:app"


@pytest.fixture(scope="module")
def scripts() -> ScriptDirectory:
    """Read the Alembic scripts of the repository.

    :return: The script directory of ``migrations/``.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


@pytest.fixture(scope="module")
def notes_script(scripts: ScriptDirectory) -> Script:
    """Find the revision that adds the observation column.

    :param scripts: The script directory.
    :return: The script of the revision.
    """
    script = scripts.get_revision(NOTES_REVISION)
    assert script is not None
    return script


def _function(script: Script, name: str) -> ast.FunctionDef:
    """Find a top-level function in the source of a revision.

    :param script: The script of the revision.
    :param name: Name of the function.
    :return: The function node.
    :raises AssertionError: If the module has no such function.
    """
    tree = ast.parse(Path(script.path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{script.path} has no function {name}")


def _body(function: ast.FunctionDef) -> list[str]:
    """List the statements of a function after its docstring, as source text.

    :param function: The function node.
    :return: The source of each statement.
    """
    return [ast.unparse(node) for node in function.body[1:]]


def test_alembic_has_exactly_one_head_and_it_is_the_observation_revision(scripts: ScriptDirectory) -> None:
    """Check that the migrations did not fork: one head, the revision that adds the observation.

    :param scripts: The script directory.
    """
    assert scripts.get_heads() == [NOTES_REVISION]
    assert scripts.get_current_head() == NOTES_REVISION


def test_observation_revision_follows_the_previous_head(notes_script: Script, scripts: ScriptDirectory) -> None:
    """Check that the new revision comes right after the previous head and is the only one that does.

    :param notes_script: The script of the new revision.
    :param scripts: The script directory.
    """
    assert notes_script.down_revision == PREVIOUS_REVISION
    assert notes_script.nextrev == frozenset()
    children = [script.revision for script in scripts.walk_revisions() if script.down_revision == PREVIOUS_REVISION]
    assert children == [NOTES_REVISION]


def test_upgrade_adds_the_nullable_text_column_to_skinfolds(notes_script: Script) -> None:
    """Check, in the source of the revision, that the upgrade only adds ``skinfolds.observacoes`` as nullable text.

    :param notes_script: The script of the new revision.
    """
    function = _function(notes_script, "upgrade")

    assert _body(function) == [
        "with op.batch_alter_table('skinfolds', schema=None) as batch_op:\n"
        "    batch_op.add_column(sa.Column('observacoes', sa.Text(), nullable=True))"
    ]
    assert ast.unparse(function.returns) == "None"


def test_downgrade_drops_the_column_it_added(notes_script: Script) -> None:
    """Check, in the source of the revision, that the downgrade only drops ``skinfolds.observacoes``.

    :param notes_script: The script of the new revision.
    """
    function = _function(notes_script, "downgrade")

    assert _body(function) == [
        "with op.batch_alter_table('skinfolds', schema=None) as batch_op:\n    batch_op.drop_column('observacoes')"
    ]
    assert ast.unparse(function.returns) == "None"


def test_observation_revision_is_documented_and_has_no_generated_comments(notes_script: Script) -> None:
    """Check the module docstring header of the revision, the docstrings of both steps and the absence of comments.

    :param notes_script: The script of the new revision.
    """
    source = Path(notes_script.path).read_text(encoding="utf-8")

    header = ast.get_docstring(ast.parse(source), clean=False) or ""
    assert f"Revision ID: {NOTES_REVISION}" in header and f"Revises: {PREVIOUS_REVISION}" in header
    assert "Create Date:" in header
    assert all(ast.get_docstring(_function(notes_script, name)) for name in ("upgrade", "downgrade"))
    assert [line for line in source.splitlines() if "#" in line and "pragma: allowlist secret" not in line] == []
    assert source.count("# pragma: allowlist secret") == 2


def test_upgrade_and_downgrade_change_a_database_like_the_one_before(notes_script: Script) -> None:
    """Run the two steps on an in-memory SQLite table shaped like the previous ``skinfolds`` and inspect the result.

    :param notes_script: The script of the new revision.
    """
    module: ModuleType = notes_script.module
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE skinfolds "
            "(id INTEGER NOT NULL PRIMARY KEY, patient_id INTEGER NOT NULL, pa VARCHAR(6) NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO skinfolds (id, patient_id, pa) VALUES (1, 7, '12/8')")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        column = {item["name"]: item for item in sa.inspect(connection).get_columns("skinfolds")}["observacoes"]
        assert isinstance(column["type"], sa.Text) and column["nullable"] is True and column["default"] is None
        assert connection.exec_driver_sql("SELECT id, pa, observacoes FROM skinfolds").all() == [(1, "12/8", None)]
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert [item["name"] for item in sa.inspect(connection).get_columns("skinfolds")] == ["id", "patient_id", "pa"]
        assert connection.exec_driver_sql("SELECT id, pa FROM skinfolds").all() == [(1, "12/8")]


def test_model_column_matches_the_migration() -> None:
    """Check that the model declares the same column as the migration: nullable text without any default."""
    column = SkinFolds.__table__.c.observacoes

    assert isinstance(column.type, sa.Text) and column.nullable is True
    assert column.default is None and column.server_default is None


def test_procfile_runs_the_migrations_before_the_release_goes_live() -> None:
    """Check the Procfile: a release step that upgrades the database, and the web line as it was."""
    lines = PROCFILE.read_text(encoding="utf-8").splitlines()

    assert lines == [RELEASE_LINE, WEB_LINE]
