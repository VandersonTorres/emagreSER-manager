"""Markup, access and search tests of the patient pages: list, forms, record, custom history and delete confirmation."""

import json
import re
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup, Tag
from flask import Flask, render_template, url_for
from flask.testing import FlaskClient
from flask_login import login_user

from app.models import AnthropometricEvaluation, Patients, User, db
from tests.aliases import ClientFactory, SeedData
from tests.patient_cases import FIXED_EVALUATION

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"
PATIENT_TEMPLATES = sorted((TEMPLATES_DIR / "admin" / "patients").glob("*.html"))
STATIC_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
CHART_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
CHART_INTEGRITY = "sha384-bs/nf9FbdNouRbMiFcrcZfLXYPKiPaGVGplVbv7dLGECccEXDW+S3zjqSKR5ZEaD"  # pragma: allowlist secret
FORM_PAGES = ("add_patient", "edit_patient", "add_anthro", "edit_anthro", "add_skinfold", "edit_skinfold")
ACTION_LABELS = ["Ver ficha", "Editar", "Nova avaliação", "Nova bioimpedância", "Remover"]


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


def _page(client: FlaskClient, url: str) -> BeautifulSoup:
    """Open a page that must answer 200 and parse it.

    :param client: Test client.
    :param url: URL path of the page.
    :return: The parsed page.
    """
    response = client.get(url)
    assert response.status_code == 200, f"GET {url}: {response.status_code}"
    return _soup(response.get_data(as_text=True))


def _links_with_text(soup: BeautifulSoup, text: str) -> list[str]:
    """List the targets of the links whose visible text is the given one.

    :param soup: Parsed page.
    :param text: Visible text of the link, ignoring icons and surrounding spaces.
    :return: The href of each matching link.
    """
    return [link["href"] for link in soup.select("a[href]") if link.get_text().strip() == text]


def _item(soup: BeautifulSoup, name: str) -> Tag:
    """Find the list item of a patient.

    :param soup: Parsed list page.
    :param name: Name of the patient.
    :return: The list item.
    :raises AssertionError: If the patient is not in the list.
    """
    for item in soup.select("#patients-list > ul > li"):
        link = item.select_one(".patient-name")
        if link is not None and link.get_text().strip() == name:
            return item
    raise AssertionError(f"{name} is not in the list")


def _menu_labels(item: Tag) -> list[str]:
    """List the entries of the actions menu of a patient item.

    :param item: List item of the patient.
    :return: The visible text of each menu entry.
    """
    return [entry.get_text().strip() for entry in item.select(".dropdown-menu .dropdown-item")]


def test_list_shows_the_data_and_the_actions_of_each_patient(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check name, CPF, phone, e-mail, the actions menu and the contact buttons of a patient in the list.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    patient_id = int(seed["patient_nutritionist"])
    soup = _page(client_admin, _url(app, "patients.list_patients"))

    item = _item(soup, "Paciente Teste 1")

    text = item.get_text(" ", strip=True)
    assert "000.000.000-11" in text and "(31) 91111-0001" in text and "paciente1@test.local" in text
    assert _menu_labels(item) == ACTION_LABELS
    links = {entry.get_text().strip(): entry["href"] for entry in item.select(".dropdown-menu a")}
    assert links == {
        "Ver ficha": _url(app, "patients.view_patient", id=patient_id),
        "Editar": _url(app, "patients.edit_patient", id=patient_id),
        "Nova avaliação": _url(app, "patients.add_anthro", patient_id=patient_id),
        "Nova bioimpedância": _url(app, "patients.add_skinfold", patient_id=patient_id),
        "Remover": _url(app, "patients.delete_patient", id=patient_id),
    }
    toggle = item.select_one(".patient-menu-toggle")
    assert toggle is not None and toggle["data-bs-toggle"] == "dropdown" and "⋯" in toggle.get_text()
    assert item.select_one("a[href='tel:31911110001']") is not None
    assert item.select_one("a[href='https://wa.me/5531911110001']") is not None


def test_list_markup_keeps_what_the_pagination_needs(app: Flask, client_admin: FlaskClient) -> None:
    """Check the list structure the pagination script relies on, and that the list is always visible.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _page(client_admin, _url(app, "patients.list_patients"))

    listing = soup.select_one("#patients-list")
    assert listing is not None and "display" not in str(listing.get("style", ""))
    assert len(soup.select("#patients-list > ul > li")) == len(soup.select("#patients-list ul li"))
    assert len(soup.select("#patients-list > ul > li")) >= 3
    assert soup.select_one("#patients-list > #pagination-controls") is not None
    assert soup.find(id="toggle-patients") is None
    assert "Mostrar" not in soup.get_text()
    assert _links_with_text(soup, "Novo paciente") == [_url(app, "patients.add_patient")]
    assert soup.select_one("h1.page-header-title").get_text() == "Pacientes"


@pytest.mark.parametrize(
    "phone, tel, whatsapp",
    [
        ("(31) 91111-0001", "tel:31911110001", "https://wa.me/5531911110001"),
        ("(31) 3333-4444", "tel:3133334444", "https://wa.me/553133334444"),
        ("+55 31 91111-0001", "tel:5531911110001", "https://wa.me/5531911110001"),
        ("31.91111.0001", "tel:31911110001", "https://wa.me/5531911110001"),
    ],
)
def test_contact_buttons_use_the_digits_of_the_phone(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int], phone: str, tel: str, whatsapp: str
) -> None:
    """Check the tel: link and the WhatsApp link, with the country code added when the number has 10 or 11 digits.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    :param phone: Phone stored in the record.
    :param tel: Expected tel: link.
    :param whatsapp: Expected WhatsApp link.
    """
    case_patients("Paciente Contato", tel_number=phone)

    item = _item(_page(client_admin, _url(app, "patients.list_patients")), "Paciente Contato")

    assert [link["href"] for link in item.select(".patient-actions > a")] == [tel, whatsapp]


def test_patient_without_a_phone_has_no_contact_buttons(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that a record without any digit in the phone gets neither the call nor the WhatsApp button.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Sem Telefone", tel_number="sem telefone")

    item = _item(_page(client_admin, _url(app, "patients.list_patients")), "Paciente Sem Telefone")
    record = _page(client_admin, _url(app, "patients.view_patient", id=patient_id))

    assert item.select(".patient-actions > a") == []
    assert record.select("a[href^='tel:'], a[href^='https://wa.me/']") == []


@pytest.mark.parametrize("role, sees_remove", [("admin", True), ("secretary", True), ("nutritionist", False)])
def test_remove_is_only_offered_to_roles_that_may_remove(
    app: Flask, seed: SeedData, client_for: ClientFactory, role: str, sees_remove: bool
) -> None:
    """Check the Remover entry of the list menu and the Remover button of the record by role.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param role: Role under test.
    :param sees_remove: Whether the role is offered the removal.
    """
    client = client_for(role)
    delete_url = _url(app, "patients.delete_patient", id=int(seed["patient_nutritionist"]))

    listing = _page(client, _url(app, "patients.list_patients"))
    record = _page(client, _url(app, "patients.view_patient", id=int(seed["patient_nutritionist"])))

    assert ("Remover" in _menu_labels(_item(listing, "Paciente Teste 1"))) is sees_remove
    assert (listing.select_one(f"a[href='{delete_url}']") is not None) is sees_remove
    assert (record.select_one(f"a[href='{delete_url}']") is not None) is sees_remove
    assert (_links_with_text(record, "Remover") != []) is sees_remove


def test_nutritionist_list_only_has_their_patients(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check that the nutritionist still sees their patient and the one with a future schedule, and nobody else.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as nutritionist.
    """
    soup = _page(client_nutritionist, _url(app, "patients.list_patients"))

    names = [item.select_one(".patient-name").get_text().strip() for item in soup.select("#patients-list > ul > li")]
    assert "Paciente Teste 1" in names and "Paciente Teste 2" in names
    assert "Paciente Teste 3" not in names


def test_nutritionist_still_cannot_remove_a_patient(
    app: Flask, client_for: ClientFactory, case_patients: Callable[..., int]
) -> None:
    """Check that the backend still refuses the removal to a nutritionist and allows it to an admin.

    :param app: Flask application.
    :param client_for: Factory of test clients by role.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Para Remover", specialist="specialist_nutritionist")
    url = _url(app, "patients.delete_patient", id=patient_id)

    refused = client_for("nutritionist").post(url)

    assert refused.status_code == 302 and refused.headers["Location"].endswith("/patients")
    with app.app_context():
        assert db.session.get(Patients, patient_id) is not None
    removed = client_for("admin").post(url)
    assert removed.status_code == 302
    with app.app_context():
        assert db.session.get(Patients, patient_id) is None


def test_search_without_results_shows_the_empty_state(app: Flask, client_admin: FlaskClient) -> None:
    """Check that a search that matches nothing lists no patient and offers to clear the search.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    url = _url(app, "patients.list_patients", search="Zzz Ninguém <b>")

    soup = _page(client_admin, url)

    empty = soup.select_one(".empty-state")
    assert empty is not None and "Nenhum paciente encontrado" in empty.get_text()
    assert "Zzz Ninguém <b>" in empty.get_text()
    assert "<b>" not in str(empty)
    clear = empty.find("a", string="Limpar busca")
    assert clear is not None and clear["href"] == _url(app, "patients.list_patients")
    assert soup.select("#patients-list li, .patient-item") == []
    assert soup.select_one("#anthro-form") is None
    assert soup.select_one("input[name=search]")["value"] == "Zzz Ninguém <b>"


def test_search_with_results_lists_only_the_matches(app: Flask, client_admin: FlaskClient) -> None:
    """Check that a matching search, by name or by CPF, lists only the matching patients.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    by_name = _page(client_admin, _url(app, "patients.list_patients", search="Paciente Teste 1"))
    by_cpf = _page(client_admin, _url(app, "patients.list_patients", search="000.000.000-12"))

    assert [item.select_one(".patient-name").get_text() for item in by_name.select("#patients-list > ul > li")] == [
        "Paciente Teste 1"
    ]
    assert [item.select_one(".patient-name").get_text() for item in by_cpf.select("#patients-list > ul > li")] == [
        "Paciente Teste 2"
    ]
    assert by_name.select_one(".empty-state") is None
    assert by_name.find("a", string="Limpar busca") is not None


def test_empty_database_shows_the_empty_state_with_the_new_patient_action(app: Flask, seed: SeedData) -> None:
    """Check the list page when there is no patient at all.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/patients-manager/patients"):
        login_user(db.session.get(User, int(seed["user_admin"])))
        html = render_template("admin/patients/list_patients.html", patients=[], search_empty=False, search_query="")

    soup = _soup(html)
    empty = soup.select_one(".empty-state")
    assert empty is not None and "Ainda não existem pacientes cadastrados" in empty.get_text()
    action = empty.find("a", string="Novo paciente")
    assert action is not None and action["href"] == _url(app, "patients.add_patient")
    assert soup.select("#patients-list") == []


def test_quick_forms_keep_their_selects_and_url_templates(app: Flask, client_admin: FlaskClient) -> None:
    """Check the evaluation and bioimpedance shortcuts: the selects, the choices and the URL templates.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    response = client_admin.get(_url(app, "patients.list_patients"))

    html = response.get_data(as_text=True)
    soup = _soup(html)
    for select_id in ("patient_select", "patient_select_skinfold"):
        select = soup.select_one(f"select#{select_id}[name=patient_id]")
        assert select is not None
        assert len(select.select("option")) == len(soup.select("#patients-list > ul > li")) + 1
    assert f'var addAnthroUrlTemplate = "{_url(app, "patients.add_anthro", patient_id=0)}"' in html
    assert f'var addSkinfoldUrlTemplate = "{_url(app, "patients.add_skinfold", patient_id=0)}"' in html
    assert "onclick" not in html


def _complete_record(app: Flask, client: FlaskClient, ids: dict[str, int], extra: int = 0) -> BeautifulSoup:
    """Open the record of the complete patient, after adding more evaluations to it.

    :param app: Flask application.
    :param client: Test client.
    :param ids: Ids returned by the complete_patient fixture.
    :param extra: Number of evaluations to add before the fixed one.
    :return: The parsed record page.
    """
    with app.app_context():
        for number in range(extra):
            values = {**FIXED_EVALUATION, "data_avaliacao": date(2026, 4, 1) - timedelta(days=number)}
            db.session.add(AnthropometricEvaluation(patient_id=ids["patient"], **values))
        db.session.commit()
    return _page(client, _url(app, "patients.view_patient", id=ids["patient"]))


def test_record_header_shows_the_patient_and_the_actions(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check the header card of the record: contact data, professional, start date and the five actions.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient_id = complete_patient["patient"]
    soup = _complete_record(app, client_admin, complete_patient)

    header = soup.select_one(".patient-header")
    assert header is not None
    assert header.select_one("h1").get_text().strip() == "Paciente Completo Base"
    text = header.get_text(" ", strip=True)
    assert "(11) 98888-7777" in text and "completo@example.com" in text and "Profissional Teste 2" in text
    assert "Paciente desde" in text and re.search(r"\d{2}/\d{2}/\d{4}", text)
    assert header.select_one("span.patient-age")["data-birth-date"] == "1980-07-20"
    assert header.select_one("a[href='tel:11988887777']") is not None
    assert header.select_one("a[href='https://wa.me/5511988887777']") is not None
    assert header.select_one("a[href='mailto:completo@example.com']") is not None
    actions = {link.get_text().strip(): link["href"] for link in header.select(".patient-header-actions a")}
    assert actions == {
        "Editar": _url(app, "patients.edit_patient", id=patient_id),
        "Nova avaliação": _url(app, "patients.add_anthro", patient_id=patient_id),
        "Nova bioimpedância": _url(app, "patients.add_skinfold", patient_id=patient_id),
        "Histórico personalizado": _url(
            app, "patients.view_custom_history", id=patient_id, pat_name="Paciente Completo Base"
        ),
        "Remover": _url(app, "patients.delete_patient", id=patient_id),
    }


def test_record_tabs_are_accessible_and_keyed_for_the_url_hash(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check the four tabs: roles, links between tabs and panels, the first one active and the keys of the hash.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    soup = _complete_record(app, client_admin, complete_patient)

    nav = soup.select_one("ul.nav.nav-tabs[role=tablist]")
    assert nav is not None and nav.get("aria-label")
    tabs = nav.select("button[role=tab]")
    assert [tab["data-tab-key"] for tab in tabs] == ["dados", "avaliacoes", "bioimpedancia", "evolucao"]
    assert [tab["aria-selected"] for tab in tabs] == ["true", "false", "false", "false"]
    for tab in tabs:
        panel = soup.select_one(tab["data-bs-target"])
        assert panel is not None and panel["role"] == "tabpanel"
        assert panel["id"] == tab["aria-controls"] and panel["aria-labelledby"] == tab["id"]
        assert tab["data-bs-toggle"] == "tab"
    assert [bool("active" in pane["class"]) for pane in soup.select(".tab-pane")] == [True, False, False, False]
    assert [tab.get_text(" ", strip=True) for tab in tabs] == ["Dados", "Avaliações 1", "Bioimpedância 1", "Evolução"]


def test_record_tables_keep_their_columns_and_confirmations(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check the 14 and 11 columns, the extra rows, the show-more buttons and the delete forms of the record.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient_id = complete_patient["patient"]
    soup = _complete_record(app, client_admin, complete_patient, extra=6)

    anthro = soup.select_one("table#anthro-table")
    skinfold = soup.select_one("table#skinfold-table")
    assert anthro is not None and skinfold is not None
    assert len(anthro.select("thead th")) == 14 and len(skinfold.select("thead th")) == 11
    assert len(anthro.select("tbody tr")) == 7 and len(anthro.select("tbody tr.record-row-extra")) == 2
    assert len(skinfold.select("tbody tr")) == 1 and skinfold.select("tbody tr.record-row-extra") == []
    assert all(cell.has_attr("data-label") for cell in anthro.select("tbody td"))
    toggle = soup.select_one("#toggleAnthro")
    assert toggle is not None and toggle["data-table"] == "anthro-table" and toggle["aria-expanded"] == "false"
    assert soup.select_one("#toggleSkinfold") is None
    delete = anthro.select_one("form[action*='/evaluation/delete/']")
    assert delete is not None and delete["method"] == "post" and delete["data-confirm"]
    assert delete["action"] == _url(
        app,
        "patients.delete_anthropometric_evaluation",
        patient_id=patient_id,
        evaluation_id=complete_patient["evaluation"],
    )
    skinfold_delete = skinfold.select_one("form[action*='/skinfold/delete/']")
    assert skinfold_delete is not None and skinfold_delete["method"] == "post" and skinfold_delete["data-confirm"]
    html = str(soup)
    assert "onsubmit" not in html and "display: table-row" not in html


def test_record_chart_and_empty_states(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int], case_patients: Callable[..., int]
) -> None:
    """Check the weight chart data and its pinned library, and the empty states of a patient without records.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param case_patients: Factory of temporary patients.
    """
    with app.app_context():
        from app.models import SkinFolds

        for number, weight in enumerate((72.5, 71.0), start=1):
            db.session.add(
                SkinFolds(
                    patient_id=complete_patient["patient"],
                    data_medicao=date(2026, 6, number),
                    altura=1.7,
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
    with_chart = _page(client_admin, _url(app, "patients.view_patient", id=complete_patient["patient"]))
    empty_patient = case_patients("Paciente Sem Registros")
    without = _page(client_admin, _url(app, "patients.view_patient", id=empty_patient))

    canvas = with_chart.select_one("canvas#weightChart")
    assert canvas is not None and canvas["role"] == "img" and canvas["aria-label"]
    assert json.loads(canvas["data-dates"]) == ["10/05/2026", "01/06/2026", "02/06/2026"]
    assert json.loads(canvas["data-weights"]) == [70.0, 72.5, 71.0]
    script = with_chart.select_one(f"script[src='{CHART_URL}']")
    assert script is not None and script["integrity"] == CHART_INTEGRITY and script["crossorigin"] == "anonymous"
    assert with_chart.select_one("a[href*='view-custom-history']") is not None
    assert without.select_one("canvas") is None and without.select(f"script[src='{CHART_URL}']") == []
    assert [
        state.select_one(".empty-state-title").get_text() for state in without.select(".tab-pane .empty-state")
    ] == [
        "Não há avaliações antropométricas registradas",
        "Não há registros de bioimpedância",
        "Ainda não há medições para o gráfico",
    ]


def test_chart_library_only_loads_where_a_chart_is_shown(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check that the list and the forms do not load Chart.js, and that the history page pins it.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    patient = int(seed["patient_nutritionist"])
    history_url = _url(app, "patients.view_custom_history", id=patient, pat_name="Paciente Teste 1")

    for url in (
        _url(app, "patients.list_patients"),
        _url(app, "patients.add_patient"),
        _url(app, "patients.edit_patient", id=patient),
        _url(app, "patients.add_anthro", patient_id=patient),
    ):
        assert "Chart.js" not in client_admin.get(url).get_data(as_text=True), url
    history = _page(client_admin, history_url)
    script = history.select_one(f"script[src='{CHART_URL}']")
    assert script is not None and script["integrity"] == CHART_INTEGRITY and script["crossorigin"] == "anonymous"
    assert "jsdelivr.net/npm/chart.js" not in str(history)
    assert history.select_one("canvas#evolutionsChart[data-dates][data-weights]") is not None
    assert history.select_one("button[data-print]") is not None


def test_custom_history_shows_the_summary_or_the_empty_state(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check the history of a patient with evaluations and of one without.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    with_data = _page(
        client_admin,
        _url(app, "patients.view_custom_history", id=int(seed["patient_nutritionist"]), pat_name="Paciente Teste 1"),
    )
    without = _page(
        client_admin,
        _url(app, "patients.view_custom_history", id=int(seed["patient_schedule"]), pat_name="Paciente Teste 2"),
    )

    text = with_data.get_text(" ", strip=True)
    for label in ("IMC atual", "Peso inicial", "Peso atual", "Peso ideal", "Resultado final", "Histórico de evoluções"):
        assert label in text
    assert with_data.select_one(".history-message") is not None
    back = with_data.select_one("a.page-header-back")
    assert back is not None and back["href"].endswith("#evolucao")
    assert without.select_one(".empty-state") is not None and without.select_one("canvas") is None


def test_delete_confirmation_uses_the_confirm_card(app: Flask, seed: SeedData, client_admin: FlaskClient) -> None:
    """Check the removal confirmation: the patient, a POST to the same URL, and the way back.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    url = _url(app, "patients.delete_patient", id=int(seed["patient_other"]))

    soup = _page(client_admin, url)

    card = soup.select_one(".card.confirm-card")
    assert card is not None
    assert "Paciente Teste 3" in card.get_text() and "000.000.000-13" in card.get_text()
    form = card.select_one("form[method=post]")
    assert form is not None and not form.get("action")
    assert form.select_one("button[type=submit]").get_text().strip() == "Confirmar remoção"
    assert form.find("a", string="Cancelar")["href"] == _url(app, "patients.list_patients")


def _all_patient_urls(app: Flask, seed: SeedData, complete: dict[str, int]) -> dict[str, str]:
    """List one URL of every page of the patient area.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param complete: Ids of the complete patient fixture.
    :return: The URL path of each page, keyed by a short name.
    """
    patient = int(seed["patient_nutritionist"])
    return {
        "list": _url(app, "patients.list_patients"),
        "add_patient": _url(app, "patients.add_patient"),
        "edit_patient": _url(app, "patients.edit_patient", id=patient),
        "view_patient": _url(app, "patients.view_patient", id=patient),
        "history": _url(app, "patients.view_custom_history", id=patient, pat_name="Paciente Teste 1"),
        "delete_patient": _url(app, "patients.delete_patient", id=patient),
        "add_anthro": _url(app, "patients.add_anthro", patient_id=patient),
        "edit_anthro": _url(
            app, "patients.edit_anthro", patient_id=complete["patient"], evaluation_id=complete["evaluation"]
        ),
        "add_skinfold": _url(app, "patients.add_skinfold", patient_id=patient),
        "edit_skinfold": _url(
            app, "patients.edit_skinfold", patient_id=complete["patient"], skinfold_id=complete["skinfold"]
        ),
    }


def test_no_patient_page_uses_the_compatibility_wrapper(
    app: Flask, seed: SeedData, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check that every redesigned page of the area renders without the compatibility wrapper and with its title.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    for name, url in _all_patient_urls(app, seed, complete_patient).items():
        soup = _page(client_admin, url)

        assert soup.select_one(".app-content.compat") is None, name
        assert soup.select_one(".app-content") is not None, name
        assert soup.select_one("main h1") is not None, name
        assert soup.title is not None and soup.title.get_text().endswith("EmagreSER"), name


@pytest.mark.parametrize("page", FORM_PAGES)
def test_every_control_of_a_form_has_a_label(
    app: Flask, seed: SeedData, client_admin: FlaskClient, complete_patient: dict[str, int], page: str
) -> None:
    """Check that each visible control of a form has an id and a label that points to it, and ids are unique.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param page: Name of the page under test.
    """
    soup = _page(client_admin, _all_patient_urls(app, seed, complete_patient)[page])

    form = soup.select_one("main form")
    assert form is not None
    controls = [
        control
        for control in form.select("input, select, textarea")
        if control.get("type") not in {"hidden", "submit"} and control.get("name")
    ]
    labels = {label.get("for") for label in form.select("label[for]")}
    ids = [control.get("id") for control in controls]
    assert all(ids) and len(set(ids)) == len(ids), page
    assert set(ids) <= labels, (page, set(ids) - labels)


def test_patient_forms_use_the_right_input_types(
    app: Flask, seed: SeedData, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check phone, e-mail and numeric fields: input types, keyboards and the autofill choice.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    urls = _all_patient_urls(app, seed, complete_patient)

    add = _page(client_admin, urls["add_patient"])
    edit = _page(client_admin, urls["edit_patient"])

    for soup, phone in ((add, "phone"), (edit, "tel_number")):
        assert soup.select_one(f"input#{phone}[type=tel]") is not None
        assert soup.select_one("input#email[type=email]") is not None
        assert soup.select_one("input#cpf[inputmode=numeric]") is not None
        assert soup.select_one("input#intestine[inputmode=numeric]") is not None
        assert soup.select_one("input#water[inputmode=decimal]") is not None
        assert soup.select_one("input#birth_date[type=date]") is not None
        assert soup.select_one("input#hours[type=time]") is not None
        assert {
            control["autocomplete"]
            for control in soup.select("main form input[name], main form select[name]")
            if control.get("type") != "hidden"
        } == {"off"}
    assert [heading.get_text() for heading in add.select("section.form-section h2")] == [
        "Dados pessoais",
        "Contato",
        "Saúde e hábitos",
        "Objetivo",
    ]
    assert [heading.get_text() for heading in edit.select("section.form-section h2")] == [
        "Dados pessoais",
        "Contato",
        "Saúde e hábitos",
        "Objetivo",
    ]
    assert [button.get_text().strip() for button in edit.select("form.edit-patient-form button[type=submit]")] == [
        "Salvar alterações"
    ]
    assert edit.find("a", string="Cancelar")["href"] == urls["view_patient"]
    assert edit.select("input[type=checkbox], input[name=edit_fields]") == []
    assert all(not field.has_attr("readonly") for field in edit.select("form.edit-patient-form input[name]"))


def test_edit_page_lists_the_evaluations_and_measurements_with_edit_links(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check the lists below the edit form and their links to the edit pages.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient_id = complete_patient["patient"]
    soup = _page(client_admin, _url(app, "patients.edit_patient", id=patient_id))

    links = [link["href"] for link in soup.select("ul.list-group a.btn")]
    assert links == [
        _url(app, "patients.edit_anthro", patient_id=patient_id, evaluation_id=complete_patient["evaluation"]),
        _url(app, "patients.edit_skinfold", patient_id=patient_id, skinfold_id=complete_patient["skinfold"]),
    ]


def test_back_links_return_to_the_tab_of_the_record(
    app: Flask, seed: SeedData, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check that the pages opened from a tab of the record lead back to that tab through the URL hash.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    urls = _all_patient_urls(app, seed, complete_patient)

    for page, tab in (
        ("add_anthro", "#avaliacoes"),
        ("edit_anthro", "#avaliacoes"),
        ("add_skinfold", "#bioimpedancia"),
        ("edit_skinfold", "#bioimpedancia"),
    ):
        soup = _page(client_admin, urls[page])

        hrefs = [link["href"] for link in soup.select("main a.page-header-back, main .form-actions a")]
        assert hrefs and all(href.endswith(tab) for href in hrefs), page


def test_add_evaluation_without_measurement_asks_for_bioimpedance_first(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check the empty state of the evaluation page for a patient that never had a measurement.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Sem Medicao")

    soup = _page(client_admin, _url(app, "patients.add_anthro", patient_id=patient_id))

    assert soup.select("form.add-anthro-form") == []
    action = soup.select_one(".empty-state a.btn")
    assert action is not None and action["href"] == _url(app, "patients.add_skinfold", patient_id=patient_id)


def test_deleting_an_evaluation_and_a_measurement_still_posts_and_redirects(
    app: Flask, client_admin: FlaskClient, complete_patient: dict[str, int]
) -> None:
    """Check the delete forms of the record: both answer with a redirect to the record and remove the row.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param complete_patient: Ids of the patient with every field filled and its records.
    """
    patient_id = complete_patient["patient"]
    record = _url(app, "patients.view_patient", id=patient_id)
    soup = _page(client_admin, record)

    for selector in ("form[action*='/evaluation/delete/']", "form[action*='/skinfold/delete/']"):
        form = soup.select_one(selector)
        assert form is not None
        response = client_admin.post(form["action"])
        assert response.status_code == 302 and response.headers["Location"].endswith(record)

    with app.app_context():
        assert db.session.get(AnthropometricEvaluation, complete_patient["evaluation"]) is None


@pytest.mark.parametrize("path", PATIENT_TEMPLATES, ids=lambda path: path.name)
def test_patient_templates_have_no_comments(path: Path) -> None:
    """Check that the patient templates carry no comments, apart from tool pragmas.

    :param path: Template under test.
    """
    source = path.read_text(encoding="utf-8")

    assert "<!--" not in source
    assert [comment for comment in re.findall(r"\{#.*?#\}", source, flags=re.S) if "pragma:" not in comment] == []


@pytest.mark.parametrize(
    "name",
    [
        "list_patients",
        "add_patient",
        "edit_patient",
        "normalize_fields",
        "patient_view",
        "automate_anthro_fields",
        "chart_config",
        "add_diet",
        "anthro_age",
        "decimal_fields",
    ],
)
def test_patient_scripts_are_documented_and_tidy(name: str) -> None:
    """Check that the scripts of the patient pages are wrapped, documented and free of loose comments and logs.

    :param name: Script name without extension.
    """
    source = (STATIC_JS / f"{name}.js").read_text(encoding="utf-8")

    assert source.startswith("/**") and "\n(function () {\n" in source
    assert "console." not in source and "=>" not in re.sub(r"/\*\*.*?\*/", "", source, flags=re.S)
    for match in re.finditer(r"\bfunction\b\s*\w*\s*\(", source):
        assert source[: match.start()].rstrip().removesuffix("(").rstrip().endswith("*/"), (name, match.start())
    assert not re.search(r"^\s*//", source, flags=re.M), name
