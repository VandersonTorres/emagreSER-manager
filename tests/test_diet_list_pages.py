"""Tests of the diet list, the diet forms and the removal page: structure, actions per role, empty states and texts."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup
from flask import Flask, render_template, url_for
from flask.testing import FlaskClient
from flask_login import login_user

from app.models import Diet, Patients, User, db
from tests.aliases import ClientFactory, SeedData

APP_DIR = Path(__file__).resolve().parent.parent / "app"
SORTABLE = "https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"
SORTABLE_INTEGRITY = (
    "sha384-eeLEhtwdMwD3X9y+8P3Cn7Idl/M+w8H4uZqkgD/2eJVkWIN1yKzEj6XegJ9dL3q0"  # pragma: allowlist secret
)
DRAG_LABEL = "Arrastar para reordenar"
NO_EDIT_HINT = "Edite o PDF antes de enviar"
SEARCH_HINT = "Limpe a busca para reordenar as dietas"
REVIEW_NOTICE = "Antes de enviar, confira a última edição do PDF."


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


def _list(client: FlaskClient, app: Flask, **query: str) -> BeautifulSoup:
    """Open the diet list.

    :param client: Test client.
    :param app: Flask application.
    :param query: Query string arguments.
    :return: The parsed page.
    """
    response = client.get(_url(app, "diets.list_diets", **query))
    assert response.status_code == 200
    return _soup(response.get_data(as_text=True))


def _card(soup: BeautifulSoup, diet_id: int) -> Any:
    """Find the card of a diet in the list.

    :param soup: Parsed diet list.
    :param diet_id: Id of the diet.
    :return: The list item of the diet.
    """
    card = soup.select_one(f"#diet-list > li[data-id='{diet_id}']")
    assert card is not None, diet_id
    return card


def _texts(elements: Any) -> list[str]:
    """Read the stripped text of each element.

    :param elements: Elements of a parsed page.
    :return: The texts, in order.
    """
    return [" ".join(element.get_text().split()) for element in elements]


@pytest.fixture
def diet_without_file(app: Flask) -> Iterator[int]:
    """Create a diet with neither a PDF nor an edition, and remove it afterwards.

    :param app: Flask application.
    :return: Id of the diet (yielded).
    """
    with app.app_context():
        diet = Diet(name="Dieta Lista Sem Arquivo", description="Sem arquivo (teste)", diet_file=None, order=98)
        db.session.add(diet)
        db.session.commit()
        diet_id = diet.id
    yield diet_id
    with app.app_context():
        Diet.query.filter_by(id=diet_id).delete(synchronize_session=False)
        db.session.commit()


def test_list_has_the_header_and_the_primary_action(app: Flask, client_admin: FlaskClient) -> None:
    """Check the title of the diet list and its "Nova dieta" action.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    assert soup.select_one("h1.page-header-title").get_text() == "Dietas"
    action = soup.select_one(".page-header-actions a")
    assert action["href"] == _url(app, "diets.add_diet")
    assert "Nova dieta" in action.get_text()
    assert soup.select_one("title").get_text() == "Dietas · EmagreSER"


def test_list_search_form_keeps_the_query_parameter(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the search box sends the "query" argument and shows the searched text.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app, query="Editada")

    form = soup.select_one("form[role=search]")
    field = form.select_one("input[name=query]")
    assert form["method"] == "get" and form["action"] == _url(app, "diets.list_diets")
    assert field["value"] == "Editada"
    assert form.select_one("label[for='%s']" % field["id"]) is not None
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Buscar"


def test_every_diet_is_a_card_in_the_sortable_structure(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check #diet-list > li[data-id]: the order of the database, the handle, the name and the description.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    ids = [int(item["data-id"]) for item in soup.select("#diet-list > li[data-id]")]
    with app.app_context():
        expected = [diet.id for diet in Diet.query.order_by(Diet.order.asc(), Diet.name.asc()).all()]
    assert ids == expected
    assert soup.select_one("#diet-list")["data-reorder-url"] == _url(app, "diets.reorder_diets")
    assert soup.select_one("#diet-list")["data-reorderable"] == "true"
    card = _card(soup, int(seed["diet_a4"]))
    assert "card" in card["class"]
    assert card.select_one(".diet-name").get_text() == "Dieta Teste A4"
    assert card.select_one(".diet-description").get_text() == "Dieta ficticia (e2e)"
    handle = card.select_one(".diet-handle")
    assert handle["aria-label"] == DRAG_LABEL
    assert handle.select_one("i.bi-grip-vertical") is not None
    assert handle.name != "a" and handle.get("role") == "button" and handle.get("tabindex") == "0"
    assert len(soup.select(".diet-handle")) == len(ids)


def test_the_edited_pdf_badge_and_the_send_button_follow_the_edition(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check the "PDF editado" badge, the enabled send button and the hint of a diet that was never edited.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)
    edited, plain = _card(soup, int(seed["diet_edited"])), _card(soup, int(seed["diet_a4"]))

    assert _texts(edited.select(".badge")) == ["PDF editado"]
    assert plain.select(".badge") == []
    send = edited.select_one("button.diet-send")
    assert send.get("disabled") is None
    assert send["data-bs-target"] == "#send-diet-modal" and send["data-bs-toggle"] == "modal"
    assert send["data-whatsapp-action"] == _url(app, "diets.send_diet_wpp", diet_id=int(seed["diet_edited"]))
    assert send["data-email-action"] == _url(app, "diets.send_diet_email", diet_id=int(seed["diet_edited"]))
    assert send["data-edition-url"] == _url(app, "diets.view_last_edition", id=int(seed["diet_edited"]))
    assert send["data-diet-name"] == "Dieta Teste Editada"
    assert edited.select(".diet-hint") == []
    blocked = plain.select_one("button.diet-send")
    assert blocked.get("disabled") is not None and blocked.get("data-bs-toggle") is None
    assert _texts(plain.select(".diet-hint")) == [NO_EDIT_HINT]
    assert plain.select_one(".diet-hint")["id"] in blocked["aria-describedby"].split()


def test_each_diet_has_the_grouped_actions(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the primary action and the "⋯" menu of an edited and of a never edited diet.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    for key, edited in (("diet_edited", True), ("diet_a4", False)):
        diet_id = int(seed[key])
        card = _card(soup, diet_id)
        primary = card.select_one("a.btn-primary")
        assert primary["href"] == _url(app, "diets.edit_diet", id=diet_id) and "Editar PDF" in primary.get_text()
        toggle = card.select_one(".dropdown > button[data-bs-toggle=dropdown]")
        assert "⋯" in toggle.get_text()
        items = {" ".join(link.get_text().split()): link for link in card.select(".dropdown-menu a.dropdown-item")}
        assert items["Ver PDF original"]["href"] == _url(app, "diets.view_diet", id=diet_id)
        assert items["Ver PDF original"]["target"] == "_blank" and "noopener" in items["Ver PDF original"]["rel"]
        assert items["Editar dados da dieta"]["href"] == _url(app, "diets.edit_diet_raw", id=diet_id)
        assert items["Remover"]["href"] == _url(app, "diets.delete_diet", id=diet_id)
        assert ("Ver última edição" in items) is edited
        if edited:
            assert items["Ver última edição"]["href"] == _url(app, "diets.view_last_edition", id=diet_id)
        assert list(items)[-1] == "Remover"


def test_a_diet_without_a_file_still_lists_with_its_actions(
    app: Flask, client_admin: FlaskClient, diet_without_file: int
) -> None:
    """Check that a diet with no PDF is listed, cannot be sent and keeps the menu.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param diet_without_file: Id of the diet without a PDF.
    """
    card = _card(_list(client_admin, app), diet_without_file)

    assert card.select_one("button.diet-send")["disabled"] is not None
    assert _texts(card.select(".diet-hint")) == [NO_EDIT_HINT]
    assert card.select_one(".dropdown-menu a[href$='/%d']" % diet_without_file) is not None


def test_there_is_one_send_dialog_with_the_patient_select(app: Flask, client_admin: FlaskClient) -> None:
    """Check the single send dialog: title, review notice, patient select, token and the two send buttons.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    assert len(soup.select("#send-diet-modal")) == 1
    assert len(soup.select("select[name=patient_id]")) == 1
    assert soup.select("form[id^='send-diet-form-']") == []
    modal = soup.select_one("#send-diet-modal")
    assert modal["aria-labelledby"] == "send-diet-title" and "modal" in modal["class"]
    assert modal.select_one("#send-diet-title #send-diet-name") is not None
    assert REVIEW_NOTICE in modal.get_text()
    assert modal.select_one("#send-diet-preview")["target"] == "_blank"
    form = modal.select_one("form#send-diet-form")
    assert form["method"] == "post"
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    select = form.select_one("select#send-diet-patient")
    assert select.has_attr("required")
    assert form.select_one("label[for='send-diet-patient']").get_text() == "Paciente"
    buttons = {button.get_text().strip(): button for button in form.select("button[type=submit]")}
    assert list(buttons) == ["Enviar por WhatsApp", "Enviar por e-mail"]
    with app.app_context():
        names = sorted(patient.name for patient in Patients.query.all())
    assert [option.get_text() for option in select.select("option[value]:not([value=''])")] == names


def test_the_send_dialog_lists_only_the_patients_of_the_nutritionist(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check that the nutritionist filter of the view still decides which patients the dialog offers.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as the nutritionist.
    """
    soup = _list(client_nutritionist, app)

    options = soup.select("#send-diet-patient option[value]:not([value=''])")
    assert sorted(option["value"] for option in options) == sorted(
        [str(seed["patient_nutritionist"]), str(seed["patient_schedule"])]
    )


def test_the_list_page_is_the_same_for_the_secretary(app: Flask, client_secretary: FlaskClient) -> None:
    """Check that the secretary gets the same cards, dialog and actions.

    :param app: Flask application.
    :param client_secretary: Test client logged in as secretary.
    """
    soup = _list(client_secretary, app)

    assert soup.select_one("#send-diet-modal") is not None
    assert len(soup.select(".diet-handle")) == len(soup.select("#diet-list > li"))


def test_sortable_is_pinned_and_loaded_before_the_list_script(app: Flask, client_admin: FlaskClient) -> None:
    """Check the pinned Sortable script, with its integrity hash, loaded only on this page and before diet_list.js.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    scripts = [script for script in soup.select("script[src]")]
    sources = [script["src"] for script in scripts]
    sortable = scripts[sources.index(SORTABLE)]
    assert sortable["integrity"] == SORTABLE_INTEGRITY and sortable["crossorigin"] == "anonymous"
    assert sources.index(SORTABLE) < sources.index(_url(app, "static", filename="js/diet_list.js"))
    home = client_admin.get("/").get_data(as_text=True)
    assert "sortablejs" not in home
    assert "sortablejs" not in client_admin.get(_url(app, "diets.add_diet")).get_data(as_text=True)


def test_the_list_scripts_are_files_and_never_carry_the_token(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the page has no inline script and that the script file neither holds the token nor uses dialogs.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    html = client_admin.get(_url(app, "diets.list_diets")).get_data(as_text=True)
    source = (APP_DIR / "static" / "js" / "diet_list.js").read_text(encoding="utf-8")

    inline = [script.get_text() for script in _soup(html).select("script:not([src])")]
    assert all("X-CSRFToken" not in text and "csrf" not in text.lower() for text in inline)
    assert "X-CSRFToken" not in source and "csrf_token" not in source
    assert not re.search(r"console\.|alert\(|confirm\(|prompt\(", source)
    assert "Nova ordem salva." in source
    assert "Não foi possível salvar a nova ordem. Atualize a página e tente novamente." in source


def test_search_hides_the_handles_and_explains_why(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that, with a search, the handles are gone, the hint shows and the list is not reorderable.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    response = client_admin.get(_url(app, "diets.list_diets", query="Editada"))
    soup = _soup(response.get_data(as_text=True))

    assert [int(item["data-id"]) for item in soup.select("#diet-list > li")] == [int(seed["diet_edited"])]
    assert soup.select(".diet-handle") == []
    assert soup.select_one("#diet-list")["data-reorderable"] == "false"
    assert SEARCH_HINT in soup.get_text()
    assert "1 resultado para “Editada”" in " ".join(soup.select_one(".search-summary").get_text().split())
    assert soup.select_one(".search-summary a")["href"] == _url(app, "diets.list_diets")
    assert "Limpar busca" in soup.select_one(".search-summary a").get_text()
    assert SORTABLE not in response.get_data(as_text=True)


def test_without_a_search_there_is_no_hint(app: Flask, client_admin: FlaskClient) -> None:
    """Check that the reorder hint and the summary only exist while a search is active.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app)

    assert SEARCH_HINT not in soup.get_text()
    assert soup.select(".search-summary") == []
    assert soup.select_one("#diet-order-status")["aria-live"] == "polite"


def test_a_search_without_results_shows_the_text_and_a_way_back(app: Flask, client_admin: FlaskClient) -> None:
    """Check the empty state of a search with no diet: the searched text and "Limpar busca".

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _list(client_admin, app, query="zzz inexistente")

    empty = soup.select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Nenhuma dieta encontrada"
    assert "“zzz inexistente”" in empty.select_one(".empty-state-text").get_text()
    assert empty.select_one("a.btn")["href"] == _url(app, "diets.list_diets")
    assert empty.select_one("a.btn").get_text() == "Limpar busca"
    assert soup.select("#diet-list") == [] and soup.select("#send-diet-modal") == []


def test_the_empty_list_invites_to_create_a_diet(app: Flask, seed: SeedData) -> None:
    """Check the empty state of a clinic without diets, rendered for an admin.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/"):
        login_user(db.session.get(User, int(seed["user_admin"])))
        html = render_template("admin/diets/list_diets.html", patients=[], diets=[], search_query="")

    empty = _soup(html).select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Ainda não existem dietas cadastradas"
    assert empty.select_one("a.btn")["href"] == "/diets-manager/diets/add"
    assert empty.select_one("a.btn").get_text() == "Nova dieta"
    assert _soup(html).select("#diet-list") == []


def _labelled(soup: BeautifulSoup, form_selector: str) -> list[str]:
    """List the visible controls of a form that no label points to.

    :param soup: Parsed page.
    :param form_selector: CSS selector of the form.
    :return: The names of the controls without a label.
    """
    form = soup.select_one(form_selector)
    controls = form.select("input:not([type=hidden]):not([type=radio]), select, textarea")
    return [
        str(control.get("name"))
        for control in controls
        if control.get("id") is None or form.select_one("label[for='%s']" % control["id"]) is None
    ]


def test_new_diet_page_is_a_card_form_with_linked_labels(app: Flask, client_admin: FlaskClient) -> None:
    """Check the new diet page: header, card, ids used by the script, the file filter and the way back.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get(_url(app, "diets.add_diet")).get_data(as_text=True))

    assert soup.select_one("h1.page-header-title").get_text() == "Nova dieta"
    assert soup.select_one(".page-header-back")["href"] == _url(app, "diets.list_diets")
    form = soup.select_one(".card form.add-diet-form")
    assert form["method"] == "post" and form["enctype"] == "multipart/form-data"
    assert form["action"] == _url(app, "diets.add_diet")
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert form.select_one("select#diet-select[name=name]") is not None
    other = form.select_one("#other-name-field")
    assert other.has_attr("hidden") and other.select_one("input[name=other_name]") is not None
    assert form.select_one("textarea[name=description]") is not None
    assert form.select_one("input[type=file][name=diet_file]")["accept"] == "application/pdf"
    assert _labelled(soup, "form.add-diet-form") == []
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Salvar dieta"
    cancel = form.select_one("a.btn-outline-secondary")
    assert cancel["href"] == _url(app, "diets.list_diets") and cancel.get_text() == "Cancelar"
    assert soup.select_one("script[src$='js/add_diet.js']") is not None


def test_new_diet_page_shows_the_field_errors(app: Flask, client_admin: FlaskClient) -> None:
    """Check that an empty submission shows the error next to the name and marks the field.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    response = client_admin.post(_url(app, "diets.add_diet"), data={"name": "", "description": ""})

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _texts(soup.select("#diet-select-feedback > div")) == ["Este campo é obrigatório."]
    select = soup.select_one("#diet-select")
    assert "is-invalid" in select["class"] and select["aria-invalid"] == "true"
    assert select["aria-describedby"] == "diet-select-feedback"


def test_edit_diet_page_links_the_current_file_and_warns_about_the_replacement(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check the edit page: filled form, link to the current PDF, replacement note and the way back.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    diet_id = int(seed["diet_a4"])
    soup = _soup(client_admin.get(_url(app, "diets.edit_diet_raw", id=diet_id)).get_data(as_text=True))

    assert soup.select_one("h1.page-header-title").get_text() == "Editar dados da dieta"
    form = soup.select_one(".card form.edit-diet-form")
    assert form["action"] == _url(app, "diets.edit_diet_raw", id=diet_id)
    assert form["enctype"] == "multipart/form-data"
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert form.select_one("#diet-select option[selected]")["value"] == "Dieta Teste A4"
    assert form.select_one("textarea[name=description]").get_text().strip() == "Dieta ficticia (e2e)"
    link = form.select_one("#diet_file-help a")
    assert link["href"] == "https://fixtures.test/diet-a4.pdf" and link["target"] == "_blank"
    assert "Escolher outro arquivo irá substituir o atual." in form.select_one("#diet_file-help").get_text()
    assert form.select_one("input[type=file]")["accept"] == "application/pdf"
    assert _labelled(soup, "form.edit-diet-form") == []
    assert form.select_one("a.btn-outline-secondary")["href"] == _url(app, "diets.list_diets")
    assert form.select_one("a.btn-outline-secondary").get_text() == "Cancelar"


def test_edit_diet_page_without_a_file_has_no_link(
    app: Flask, client_admin: FlaskClient, diet_without_file: int
) -> None:
    """Check that the edit page of a diet with no PDF only mentions the replacement.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param diet_without_file: Id of the diet without a PDF.
    """
    soup = _soup(client_admin.get(_url(app, "diets.edit_diet_raw", id=diet_without_file)).get_data(as_text=True))

    assert soup.select("#diet_file-help a") == []
    assert "Escolher outro arquivo irá substituir o atual." in soup.select_one("#diet_file-help").get_text()


def test_delete_diet_page_is_a_confirmation_card(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the removal page: confirmation sentence, the same POST with the token and the way back.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    diet_id = int(seed["diet_a4"])
    soup = _soup(client_admin.get(_url(app, "diets.delete_diet", id=diet_id)).get_data(as_text=True))

    card = soup.select_one(".confirm-card")
    assert card.select_one("h1").get_text() == "Remover dieta"
    assert "Tem certeza de que deseja remover Dieta Teste A4?" in card.get_text()
    form = card.select_one("form.delete-diet-form")
    assert form["method"] == "post" and form.get("action") is None
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    assert form.select_one("button[type=submit]").get_text() == "Confirmar remoção"
    assert (
        form.select_one("a")["href"] == _url(app, "diets.list_diets") and form.select_one("a").get_text() == "Cancelar"
    )


def test_removing_a_diet_still_deletes_it_and_goes_to_the_list(
    app: Flask, client_for: ClientFactory, diet_without_file: int
) -> None:
    """Check that the same POST removes the diet, flashes the message and redirects to the list.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param diet_without_file: Id of the diet without a PDF.
    """
    client = client_for("admin")

    response = client.post(_url(app, "diets.delete_diet", id=diet_without_file))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(_url(app, "diets.list_diets"))
    with app.app_context():
        assert db.session.get(Diet, diet_without_file) is None
    with client.session_transaction() as session:
        assert ("success", "Dieta 'Dieta Lista Sem Arquivo' removida com sucesso!") in session["_flashes"]
