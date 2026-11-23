"""Tests of the diet editor and viewer pages: markup, the previous editor, the empty states and the save answer."""

import hashlib
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fitz
import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from app.models import Diet, db
from app.services.pdf_annotations import apply_annotations
from tests.aliases import SeedData
from tests.backend_helpers import FakeResponse, extract_spans
from tests.pdf_fixtures import SIZES, make_pdf

APP_DIR = Path(__file__).resolve().parent.parent / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
PDFJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js"
PDFJS_WORKER_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js"
PDFJS_INTEGRITY = "sha384-lrb5efVIYR2lZw+OsuztHZzP9wpGNrhui+0VlpiHb/iPcZSCDT3CeETsL9EMQ8ih"  # pragma: allowlist secret
LEGACY_JS = STATIC_DIR / "js" / "pdf_editor_legacy.js"
LEGACY_CSS = STATIC_DIR / "css" / "pdf_editor_legacy.css"
LEGACY_TEMPLATE = TEMPLATES_DIR / "admin" / "diets" / "edit_diet_legacy.html"
LEGACY_FILES = {
    LEGACY_JS: "f45630d72e61042b97f2e3046b5e7728a29c46f691705956aaefda8586c63d00",  # pragma: allowlist secret
    LEGACY_CSS: "6ebd296544d02de98b8de0dd905f53096b6cbc15b8d44af670886d01628c5f71",  # pragma: allowlist secret
    LEGACY_TEMPLATE: "2a967e37177926059d61c7caf643252a9412fa280a3753b73fe7ba8f5f2dc351",  # pragma: allowlist secret
}
EDITOR_ASSETS = (
    STATIC_DIR / "js" / "pdf_editor.js",
    STATIC_DIR / "js" / "pdf_viewer.js",
    STATIC_DIR / "css" / "pdf_editor.css",
    STATIC_DIR / "css" / "pdf_viewer.css",
    TEMPLATES_DIR / "admin" / "diets" / "edit_diet.html",
    TEMPLATES_DIR / "admin" / "diets" / "view_diet.html",
    TEMPLATES_DIR / "admin" / "diets" / "view_last_edition.html",
    TEMPLATES_DIR / "_pdfjs_assets.html",
)


def _soup(html: str) -> BeautifulSoup:
    """Parse an HTML document.

    :param html: HTML text.
    :return: The parsed document.
    """
    return BeautifulSoup(html, "html.parser")


def _url(app: Flask, endpoint: str, **values: Any) -> str:
    """Build a URL path outside a request.

    :param app: Flask application.
    :param endpoint: Flask endpoint name.
    :param values: Arguments passed to url_for.
    :return: The URL path.
    """
    with app.test_request_context():
        return url_for(endpoint, **values)


@pytest.fixture
def diet_without_files(app: Flask) -> Iterator[int]:
    """Create a diet that has neither a PDF nor an edition, and remove it afterwards.

    :param app: Flask application.
    :return: Id of the diet (yielded).
    """
    with app.app_context():
        diet = Diet(name="Dieta Sem Arquivo", description="Sem arquivo (teste)", diet_file=None, order=99)
        db.session.add(diet)
        db.session.commit()
        diet_id = diet.id
    yield diet_id
    with app.app_context():
        db.session.delete(db.session.get(Diet, diet_id))
        db.session.commit()


@pytest.fixture
def diet_without_edition(app: Flask) -> Iterator[int]:
    """Create a diet that has a PDF but was never edited, and remove it afterwards.

    :param app: Flask application.
    :return: Id of the diet (yielded).
    """
    with app.app_context():
        diet = Diet(
            name="Dieta Nunca Editada", description="Sem edicao (teste)", diet_file="https://fixtures.test/x.pdf"
        )
        db.session.add(diet)
        db.session.commit()
        diet_id = diet.id
    yield diet_id
    with app.app_context():
        db.session.delete(db.session.get(Diet, diet_id))
        db.session.commit()


def test_editor_renders_the_responsive_editor(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the markup of the default editor: new layout, module script, toolbar, panels and the link to the old one.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    diet_id = int(seed["diet_a4"])
    response = client_admin.get(_url(app, "diets.edit_diet", id=diet_id))
    html = response.get_data(as_text=True)
    soup = _soup(html)

    assert response.status_code == 200
    root = soup.select_one("#pdfe-root")
    assert root["data-save-url"] == _url(app, "diets.edit_diet", id=diet_id)
    assert root["data-pdf-url"] == "https://fixtures.test/diet-a4.pdf"
    assert soup.select_one("script[type=module][src$='js/pdf_editor.js']") is not None
    assert soup.select_one("link[href$='css/pdf_editor.css']") is not None
    assert "pdf_editor_legacy" not in html
    legacy = soup.select_one("a[href*='legacy=1']")
    assert legacy is not None and "Usar editor antigo" in legacy.get_text()
    assert legacy["href"] == _url(app, "diets.edit_diet", id=diet_id, legacy=1)
    assert soup.select_one(".page-header a[href='%s']" % _url(app, "diets.list_diets")) is not None
    assert soup.select_one(".app-content.compat") is None
    assert soup.select_one(".app-topbar") is not None
    assert "Dieta Teste A4" in soup.select_one("h1.page-header-title").get_text()
    assert "Evite aplicar zoom" not in html
    for control in ("#pdfe-toolbar", "#pdfe-panel", "#pdfe-result", "#pdfe-frame", "#pdfe-save"):
        assert soup.select_one(control) is not None, control


def test_editor_controls_are_labelled(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that every icon button has an accessible name and that no editor part reuses a Bootstrap class.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get(_url(app, "diets.edit_diet", id=int(seed["diet_a4"]))).get_data(as_text=True))
    root = soup.select_one("#pdfe-root")

    for button in root.select("button.pdfe-icon-button"):
        assert button.get("aria-label"), button
    for field in root.select("#pdfe-panel input"):
        assert root.select_one(f"label[for='{field['id']}']") is not None, field
    classes = {name for tag in root.select("[class]") for name in tag["class"]}
    assert not {name for name in classes if re.match(r"pe-\d|pe-none|pe-auto", name)}
    assert not classes & {"modal", "modal-content", "alert"}
    assert root.select_one("#pdfe-panel")["role"] == "dialog"
    assert root.select_one("dialog#pdfe-result") is not None


def test_previous_editor_stays_at_legacy_url(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that "?legacy=1" renders the previous editor with the legacy base, stylesheet and script.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    diet_id = int(seed["diet_a4"])
    html = client_admin.get(_url(app, "diets.edit_diet", id=diet_id, legacy=1)).get_data(as_text=True)

    assert "css/legacy.css" in html
    assert "css/pdf_editor_legacy.css" in html
    assert "js/pdf_editor_legacy.js" in html
    assert "pdfe-" not in html
    assert 'id="pdf-canvas"' in html and 'id="text-modal"' in html
    assert "Evite aplicar zoom" in html
    for other in ("0", "true", ""):
        page = client_admin.get(_url(app, "diets.edit_diet", id=diet_id, legacy=other)).get_data(as_text=True)
        assert "pdfe-root" in page, other


def test_previous_editor_files_are_frozen() -> None:
    """Check that the previous editor template, script and stylesheet keep the content they had before."""
    for path, digest in LEGACY_FILES.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path.name


def test_previous_editor_template_only_changes_the_asset_names() -> None:
    """Check that the previous editor template points at the legacy script and stylesheet and nothing else."""
    source = LEGACY_TEMPLATE.read_text(encoding="utf-8")

    assert source.startswith('{% extends "base_legacy.html" %}')
    assert "css/pdf_editor_legacy.css" in source and "js/pdf_editor_legacy.js" in source
    assert "js/pdf_editor.js" not in source and "css/pdf_editor.css" not in source
    assert PDFJS_URL in source and PDFJS_WORKER_URL in source


def test_obsolete_viewer_script_is_gone() -> None:
    """Check that the broken shared viewer script was removed."""
    assert not (STATIC_DIR / "js" / "render_diet.js").exists()


def test_last_edition_without_edition_shows_the_empty_state(
    app: Flask, diet_without_edition: int, client_admin: FlaskClient
) -> None:
    """Check that a diet that was never edited answers 200 with an empty state instead of a viewer.

    :param app: Flask application.
    :param diet_without_edition: Id of a diet with a PDF and no edition.
    :param client_admin: Test client logged in as admin.
    """
    response = client_admin.get(_url(app, "diets.view_last_edition", id=diet_without_edition))
    html = response.get_data(as_text=True)
    soup = _soup(html)

    assert response.status_code == 200
    assert "Esta dieta ainda não foi editada" in soup.select_one(".empty-state-title").get_text()
    assert soup.select_one(".empty-state a.btn")["href"] == _url(app, "diets.edit_diet", id=diet_without_edition)
    assert soup.select_one("[data-pdf-viewer]") is None
    assert "/uploads/temp_files/" not in html
    assert soup.select_one(".app-content.compat") is None


def test_last_edition_without_any_file_has_no_action(
    app: Flask, diet_without_files: int, client_admin: FlaskClient
) -> None:
    """Check the empty states of a diet that has no PDF at all.

    :param app: Flask application.
    :param diet_without_files: Id of a diet without PDF and without edition.
    :param client_admin: Test client logged in as admin.
    """
    edition = _soup(
        client_admin.get(_url(app, "diets.view_last_edition", id=diet_without_files)).get_data(as_text=True)
    )
    original = _soup(client_admin.get(_url(app, "diets.view_diet", id=diet_without_files)).get_data(as_text=True))

    assert edition.select_one(".empty-state") is not None and edition.select_one(".empty-state a") is None
    assert "não possui arquivo" in original.select_one(".empty-state-title").get_text()
    assert original.select_one("[data-pdf-viewer]") is None


def test_view_pages_use_the_shared_viewer(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that the original and the edited views render the shared viewer in the new layout, with their links.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    original = client_admin.get(_url(app, "diets.view_diet", id=int(seed["diet_a4"])))
    edited = client_admin.get(_url(app, "diets.view_last_edition", id=int(seed["diet_edited"])))

    for response in (original, edited):
        html = response.get_data(as_text=True)
        soup = _soup(html)
        assert response.status_code == 200
        assert soup.select_one("script[type=module][src$='js/pdf_viewer.js']") is not None
        assert soup.select_one("link[href$='css/pdf_viewer.css']") is not None
        assert soup.select_one("[data-pdf-viewer]") is not None
        assert soup.select_one(".app-content.compat") is None
        assert "render_diet.js" not in html and "pdf_editor.css" not in html
        assert soup.select_one(".page-header a[href='%s']" % _url(app, "diets.list_diets")) is not None
    assert _soup(original.get_data(as_text=True)).select_one("[data-pdf-viewer]")["data-pdf-viewer"] == (
        "https://fixtures.test/diet-a4.pdf"
    )
    edited_file = str(seed["diet_edited_file"])
    edited_soup = _soup(edited.get_data(as_text=True))
    assert edited_soup.select_one("[data-pdf-viewer]")["data-pdf-viewer"] == _url(
        app, "diets.serve_temp_file", filename=edited_file
    )
    assert (
        edited_soup.select_one("a[href='%s']" % _url(app, "diets.download_temp_diet", filename=edited_file)) is not None
    )
    assert "Baixar Arquivo Original" in original.get_data(as_text=True)


@pytest.mark.parametrize(
    "endpoint, key",
    [("diets.edit_diet", "diet_a4"), ("diets.view_diet", "diet_a4"), ("diets.view_last_edition", "diet_edited")],
)
def test_pdfjs_script_is_pinned_with_integrity(
    app: Flask, seed: SeedData, client_admin: FlaskClient, endpoint: str, key: str
) -> None:
    """Check that pages loading pdf.js pin the 3.4.120 build with its SRI hash and keep the worker address.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param endpoint: Endpoint of the page.
    :param key: Seed key of the diet.
    """
    html = client_admin.get(_url(app, endpoint, id=int(seed[key]))).get_data(as_text=True)
    soup = _soup(html)

    tag = soup.select_one("script[src='%s']" % PDFJS_URL)
    assert tag is not None
    assert tag["integrity"] == PDFJS_INTEGRITY
    assert tag["crossorigin"] == "anonymous"
    assert PDFJS_WORKER_URL in html
    assert html.index(PDFJS_URL) < html.index("workerSrc") < html.index("js/pdf_")


def test_editor_assets_have_no_alert_confirm_or_console() -> None:
    """Check that the new editor and viewer never call alert(), confirm() or console.log()."""
    for path in EDITOR_ASSETS:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(alert|confirm|prompt)\(", source), path.name
        assert "console." not in source, path.name
        assert "pdf-canvas" not in source, path.name


def test_new_assets_have_no_loose_comments() -> None:
    """Check that the new scripts and templates carry no line comments and the stylesheets only section headings."""
    for path in (STATIC_DIR / "js" / "pdf_editor.js", STATIC_DIR / "js" / "pdf_viewer.js"):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert not [line for line in lines if line.strip().startswith("//")], path.name
    for path in (STATIC_DIR / "css" / "pdf_editor.css", STATIC_DIR / "css" / "pdf_viewer.css"):
        comments = re.findall(r"/\*.*?\*/", path.read_text(encoding="utf-8"), flags=re.S)
        assert all("\n" not in comment for comment in comments), path.name
    for path in EDITOR_ASSETS:
        if path.suffix == ".html":
            assert "<!--" not in path.read_text(encoding="utf-8"), path.name


def test_save_answer_keeps_its_fields(
    app: Flask, seed: SeedData, client_admin: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check the JSON answer of a successful save: same fields and values the first editor relied on.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    pdf = make_pdf(*SIZES["a4_596x842"])
    monkeypatch.setattr("app.views.diets.requests.get", lambda url, *args, **kwargs: FakeResponse(pdf))
    diet_id = int(seed["diet_backend"])
    annotation = {
        "text": "Teste",
        "x": 100,
        "y": 200,
        "fontSize": 12,
        "color": "rgb(0, 0, 0)",
        "page": 1,
        "canvasWidth": 977,
        "canvasHeight": 1380,
    }

    response = client_admin.post(_url(app, "diets.edit_diet", id=diet_id), json={"annotations": [annotation]})
    empty = client_admin.post(_url(app, "diets.edit_diet", id=diet_id), json={"annotations": []})

    filename = f"dieta_personalizada_id_{diet_id}.pdf"
    assert response.status_code == 200
    assert response.get_json() == {
        "status": "success",
        "message": "PDF atualizado com sucesso!",
        "redirect_url": _url(app, "diets.list_diets"),
        "download_url": _url(app, "diets.download_temp_diet", filename=filename),
    }
    assert empty.status_code == 400
    assert empty.get_json() == {"status": "error", "message": "Não foi possível detectar alterações"}
    assert [span["text"] for span in extract_spans(Path(app.config["TEMP_UPLOAD_FOLDER"]) / filename)] == ["Teste"]


def test_apply_annotations_counts_the_written_texts(app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    """Check that the service writes valid annotations, skips the invalid ones with a warning and returns the count.

    :param app: Flask application.
    :param caplog: pytest log capture fixture.
    """
    grid = {"canvasWidth": 977, "canvasHeight": 1380}
    annotations = [
        {"text": "Pagina 1", "x": 100, "y": 200, "fontSize": 12, "color": "rgb(255, 0, 0)", "page": 1, **grid},
        {"text": "Pagina 2", "x": 300, "y": 400, "fontSize": 9, "color": "#0000ff", "page": 2, **grid},
        {"text": "Sem pagina", "x": 1, "y": 1, "fontSize": 9, "color": "#000000", "page": 3, **grid},
        {"text": "Sem grade", "x": 1, "y": 1, "fontSize": 9, "color": "#000000", "page": 1},
    ]
    logger = logging.getLogger("tests.pdf_annotations")
    doc = fitz.open(stream=make_pdf(*SIZES["a4_596x842"]), filetype="pdf")

    with app.app_context(), caplog.at_level(logging.WARNING, logger=logger.name):
        written = apply_annotations(doc, annotations, logger)

    assert written == 2
    assert [record.getMessage() for record in caplog.records] == [
        "Ignorando anotação com página inválida: 2",
        "Dimensões do canvas ausentes ou inválidas.",
    ]
    assert doc[0].get_text().strip() == "Pagina 1"
    assert doc[1].get_text().strip() == "Pagina 2"
    doc.close()
