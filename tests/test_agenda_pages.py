"""Tests of the agenda and the booking form: structure, status badges, dialogs, empty states and robust booking."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup
from flask import Flask, render_template, url_for
from flask.testing import FlaskClient
from flask_login import login_user

from app.models import Schedules, Specialists, User, db
from tests import test_clinic_dates
from tests.aliases import ClientFactory, SeedData
from tests.constants import NUTRITIONIST_USERNAME
from tests.test_clinic_dates import Freeze

OTHER_SPECIALIST = "Profissional Teste 2"
freeze_clock = test_clinic_dates.freeze_clock
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
VISIT_DAY = date(2041, 5, 6)
INVALID_DATE = "Data inválida."
NO_PATIENT = "Erro: selecione o paciente da consulta."
UNKNOWN_PATIENT = "Erro: paciente não encontrado. Selecione um paciente da lista."
NO_SPECIALIST = "Erro: selecione o profissional da consulta."
BAD_TIME = "Erro: informe uma data e hora válidas para a consulta."
CONFLICT = "Erro: já existe um agendamento para este profissional em um horário próximo. \nHorários sugeridos: "


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


def _agenda(client: FlaskClient, app: Flask, **query: str) -> BeautifulSoup:
    """Open the agenda.

    :param client: Test client.
    :param app: Flask application.
    :param query: Query string arguments.
    :return: The parsed page.
    """
    response = client.get(_url(app, "schedules.list_schedules", **query))
    assert response.status_code == 200
    return _soup(response.get_data(as_text=True))


def _texts(elements: Any) -> list[str]:
    """Read the text of each element with the spaces collapsed.

    :param elements: Elements of a parsed page.
    :return: The texts, in order.
    """
    return [" ".join(element.get_text().split()) for element in elements]


def _toasts(soup: BeautifulSoup) -> list[str]:
    """List the messages of the toast region.

    :param soup: Parsed page.
    :return: The text of each toast.
    """
    return [toast.get_text().strip() for toast in soup.select("#toast-region .toast-body")]


def _flashes(client: FlaskClient) -> list[tuple[str, str]]:
    """Read the messages waiting in the session of a client.

    :param client: Test client.
    :return: The (category, message) pairs, in order.
    """
    with client.session_transaction() as session:
        return [(category, message) for category, message in session.get("_flashes", [])]


def _card(soup: BeautifulSoup, specialist: str) -> Any:
    """Find the agenda card of a professional.

    :param soup: Parsed agenda.
    :param specialist: Name of the professional.
    :return: The card section.
    """
    for card in soup.select("section.schedule-card"):
        if card.select_one(".app-card-title").get_text() == specialist:
            return card
    raise AssertionError(f"no card for {specialist}")


def _count(app: Flask) -> int:
    """Count the schedules in the database.

    :param app: Flask application.
    :return: The number of rows.
    """
    with app.app_context():
        return Schedules.query.count()


@pytest.fixture
def visits(app: Flask, seed: SeedData) -> Iterator[dict[str, int]]:
    """Create three schedules of one far day, with a pending, a finished and an unknown status, and remove them.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :return: The ids by status (yielded; the rows are deleted at the end of the test).
    """
    rows = {
        "pendente": (datetime(2041, 5, 6, 8, 15), "pendente", seed["patient_nutritionist"]),
        "finalizado": (datetime(2041, 5, 6, 9, 45), "finalizado", seed["patient_schedule"]),
        "agendado": (datetime(2041, 5, 6, 23, 45), "agendado", seed["patient_other"]),
    }
    with app.app_context():
        created = {
            key: Schedules(patient_id=int(patient), date_time=when, specialist=NUTRITIONIST_USERNAME, status=status)
            for key, (when, status, patient) in rows.items()
        }
        db.session.add_all(created.values())
        db.session.commit()
        ids = {key: schedule.id for key, schedule in created.items()}
    yield ids
    with app.app_context():
        Schedules.query.filter(Schedules.id.in_(ids.values())).delete(synchronize_session=False)
        db.session.commit()


def test_agenda_has_the_header_and_the_booking_action(app: Flask, client_admin: FlaskClient) -> None:
    """Check the title of the agenda and its "Agendar consulta" action.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _agenda(client_admin, app)

    assert soup.select_one("h1.page-header-title").get_text() == "Agenda"
    action = soup.select_one(".page-header-actions a")
    assert action["href"] == _url(app, "schedules.schedule_action") and "Agendar consulta" in action.get_text()
    assert soup.select_one("title").get_text() == "Agenda · EmagreSER"


def test_filter_card_has_the_date_input_and_the_quick_links(app: Flask, client_admin: FlaskClient) -> None:
    """Check the filter card without a date: native date input, "Filtrar", "Hoje" and "Amanhã", no clear link.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _agenda(client_admin, app)

    form = soup.select_one("form.schedule-filter-form")
    assert form["method"] == "get" and form["action"] == _url(app, "schedules.list_schedules")
    field = form.select_one("input[type=date][name=date]")
    assert field["id"] == "schedule-date" and field.get("value") == ""
    assert form.select_one("label[for=schedule-date]").get_text() == "Exibir agendamentos por data"
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Filtrar"
    quick = {link.get_text().strip(): link for link in soup.select(".schedule-quick a")}
    assert list(quick) == ["Hoje", "Amanhã"]
    assert soup.find("a", string="Limpar filtro") is None
    assert soup.select_one(".schedule-filter-summary") is None


def test_quick_links_use_the_sao_paulo_date_at_night(
    app: Flask, client_admin: FlaskClient, freeze_clock: Freeze
) -> None:
    """Check "Hoje" and "Amanhã" at 22:30 in São Paulo, when it is already the next day in UTC.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param freeze_clock: Function that freezes the clock of the dates module.
    """
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    today = datetime.now(sao_paulo).date()
    instant = datetime(today.year, today.month, today.day, 22, 30, tzinfo=sao_paulo)
    freeze_clock(instant)

    soup = _agenda(client_admin, app)

    links = {
        link.get_text().strip(): parse_qs(urlparse(link["href"]).query)["date"]
        for link in soup.select(".schedule-quick a")
    }
    assert links == {"Hoje": [today.isoformat()], "Amanhã": [(today + timedelta(days=1)).isoformat()]}
    assert instant.astimezone(ZoneInfo("UTC")).date() == today + timedelta(days=1)


def test_the_quick_link_of_the_chosen_day_is_marked_current(
    app: Flask, client_admin: FlaskClient, freeze_clock: Freeze
) -> None:
    """Check that "Hoje" gets aria-current when the filter is today, shows the clear link and the summary.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param freeze_clock: Function that freezes the clock of the dates module.
    """
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    today = datetime.now(sao_paulo).date()
    freeze_clock(datetime(today.year, today.month, today.day, 22, 30, tzinfo=sao_paulo))

    soup = _agenda(client_admin, app, date=today.isoformat())

    current = [link.get_text().strip() for link in soup.select(".schedule-quick a[aria-current=date]")]
    assert current == ["Hoje"]
    assert soup.find("a", string="Limpar filtro")["href"] == _url(app, "schedules.list_schedules")
    assert soup.select_one("#schedule-date")["value"] == today.isoformat()
    expected = f"{WEEKDAYS[today.weekday()]}, {today.strftime('%d/%m/%Y')}"
    assert expected in soup.select_one(".schedule-filter-summary").get_text()


@pytest.mark.parametrize("value", ["abc", "2041-13-45", "06/05/2041", "2041-02-30", "2041-5-6x"])
def test_an_invalid_date_flashes_and_shows_the_list_without_a_filter(
    app: Flask, seed: SeedData, client_admin: FlaskClient, value: str
) -> None:
    """Check that a "date" that is not a day answers 200 with a message and the unfiltered agenda.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param value: Value of the "date" argument.
    """
    response = client_admin.get(_url(app, "schedules.list_schedules", date=value))

    soup = _soup(response.get_data(as_text=True))
    assert response.status_code == 200
    assert _toasts(soup) == [INVALID_DATE]
    assert soup.select_one("#schedule-date").get("value") == ""
    assert soup.find("a", string="Limpar filtro") is None
    assert soup.select_one(".schedule-filter-summary") is None
    assert _card(soup, NUTRITIONIST_USERNAME).select("tbody tr") != []


def test_an_empty_date_is_no_filter_and_no_error(app: Flask, client_admin: FlaskClient) -> None:
    """Check that "?date=" lists the agenda without a message.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _agenda(client_admin, app, date="")

    assert _toasts(soup) == []
    assert soup.find("a", string="Limpar filtro") is None


def test_the_filtered_agenda_shows_only_that_day(app: Flask, client_admin: FlaskClient, visits: dict[str, int]) -> None:
    """Check the filter: the rows of the day, the input value, the summary and the clear link.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param visits: Ids of the schedules of the far day.
    """
    soup = _agenda(client_admin, app, date=VISIT_DAY.isoformat())

    assert soup.select_one("#schedule-date")["value"] == "2041-05-06"
    assert soup.find("a", string="Limpar filtro")["href"] == _url(app, "schedules.list_schedules")
    assert "segunda-feira, 06/05/2041" in soup.select_one(".schedule-filter-summary").get_text()
    assert len(_card(soup, NUTRITIONIST_USERNAME).select("tbody tr")) == 3
    assert _card(soup, NUTRITIONIST_USERNAME).select_one(".badge").get_text() == "3 consultas"
    assert len(_card(soup, OTHER_SPECIALIST).select("tbody tr")) == 0


def test_visit_rows_show_patient_date_weekday_time_and_status(
    app: Flask, seed: SeedData, client_admin: FlaskClient, visits: dict[str, int]
) -> None:
    """Check each row: the link to the record, dd/mm/yyyy with the weekday, the time as stored and the status badge.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param visits: Ids of the schedules of the far day.
    """
    card = _card(_agenda(client_admin, app, date=VISIT_DAY.isoformat()), NUTRITIONIST_USERNAME)

    rows = card.select("tbody tr")
    assert [row.select_one("td[data-label=Horário]").get_text() for row in rows] == ["08:15", "09:45", "23:45"]
    assert [row.select_one(".badge").get_text() for row in rows] == ["Pendente", "Finalizado", "agendado"]
    assert [row.select_one(".badge")["class"][-1] for row in rows] == [
        "badge-soft-amber",
        "badge-soft-green",
        "badge-soft-neutral",
    ]
    first = rows[0]
    link = first.select_one("td[data-label=Paciente] a")
    assert link["href"] == _url(app, "patients.view_patient", id=int(seed["patient_nutritionist"]))
    assert link.get_text() == "Paciente Teste 1"
    when = first.select_one("td[data-label=Data]")
    assert when.select_one("time")["datetime"] == "2041-05-06" and when.select_one("time").get_text() == "06/05/2041"
    assert when.select_one(".schedule-weekday").get_text() == WEEKDAYS[VISIT_DAY.weekday()]
    assert [th.get_text() for th in card.select("thead th")] == ["Paciente", "Data", "Horário", "Status", "Ações"]
    for row in rows:
        assert {cell["data-label"] for cell in row.select("td")} == {"Paciente", "Data", "Horário", "Status", "Ações"}


def test_each_visit_has_a_cancel_dialog_that_names_it(
    app: Flask, seed: SeedData, client_admin: FlaskClient, visits: dict[str, int]
) -> None:
    """Check the cancel button and its dialog: patient, date, time, the warning and the POST with the token.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    :param visits: Ids of the schedules of the far day.
    """
    soup = _agenda(client_admin, app, date=VISIT_DAY.isoformat())

    for key, time in (("pendente", "08:15"), ("agendado", "23:45")):
        schedule_id = visits[key]
        button = soup.select_one(f"button[data-bs-target='#cancel-schedule-{schedule_id}']")
        assert button["data-bs-toggle"] == "modal" and button.get_text().split()[0] == "Cancelar"
        modal = soup.select_one(f"#cancel-schedule-{schedule_id}")
        assert "modal" in modal["class"] and modal["aria-labelledby"] == f"cancel-schedule-{schedule_id}-title"
        text = " ".join(modal.select_one(".modal-body").get_text().split())
        assert f"em 06/05/2041 às {time}" in text
        assert NUTRITIONIST_USERNAME in text
        assert "O agendamento será removido da agenda." in text
        form = modal.select_one("form")
        assert form["method"] == "post"
        assert form["action"] == _url(app, "schedules.delete_schedule", id=schedule_id)
        assert form.select_one("input[type=hidden][name=csrf_token]") is not None
        assert _texts(form.select(".modal-footer button")) == ["Voltar", "Cancelar agendamento"]
    pending = soup.select_one(f"#cancel-schedule-{visits['pendente']} .modal-body").get_text()
    assert "Paciente Teste 1" in pending


def test_the_cancel_form_still_removes_the_visit(app: Flask, client_admin: FlaskClient, visits: dict[str, int]) -> None:
    """Check that the same POST removes the schedule and flashes the message.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param visits: Ids of the schedules of the far day.
    """
    before = _count(app)

    response = client_admin.post(_url(app, "schedules.delete_schedule", id=visits["pendente"]))

    assert response.status_code == 302
    assert _count(app) == before - 1
    assert ("message", "Agendamento removido com sucesso!") in _flashes(client_admin)


def test_a_date_without_visits_says_so_for_each_professional(app: Flask, client_admin: FlaskClient) -> None:
    """Check the empty state of a day with no schedule, once per professional, with the date written dd/mm/yyyy.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _agenda(client_admin, app, date="2041-01-02")

    for specialist in (NUTRITIONIST_USERNAME, OTHER_SPECIALIST):
        card = _card(soup, specialist)
        assert card.select_one(".empty-state-title").get_text() == "Nenhum agendamento em 02/01/2041"
        assert card.select("table") == []
        assert card.select_one(".badge").get_text() == "0 consultas"


def test_a_professional_without_schedules_has_an_empty_state(app: Flask, client_admin: FlaskClient) -> None:
    """Check the empty state of a professional with nothing pending, next to the card that has a visit.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    """
    soup = _agenda(client_admin, app)

    assert _card(soup, NUTRITIONIST_USERNAME).select("tbody tr") != []
    empty = _card(soup, OTHER_SPECIALIST).select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Nenhum agendamento"


def test_the_nutritionist_only_sees_the_own_card(app: Flask, client_nutritionist: FlaskClient) -> None:
    """Check that the nutritionist gets the card of their own professional record and nothing else.

    :param app: Flask application.
    :param client_nutritionist: Test client logged in as the nutritionist.
    """
    soup = _agenda(client_nutritionist, app)

    assert [card.select_one(".app-card-title").get_text() for card in soup.select("section.schedule-card")] == [
        NUTRITIONIST_USERNAME
    ]
    assert OTHER_SPECIALIST not in soup.get_text()


@pytest.mark.parametrize("role, has_link", [("admin", True), ("secretary", True), ("nutritionist", False)])
def test_an_agenda_without_professionals_links_the_managers_to_the_professionals_page(
    app: Flask, seed: SeedData, role: str, has_link: bool
) -> None:
    """Check the empty state of a clinic without professionals: a link for admin and secretary only.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param role: Role of the user.
    :param has_link: Whether the empty state offers the link.
    """
    today = date(2041, 1, 2)
    with app.test_request_context("/"):
        login_user(db.session.get(User, int(seed[f"user_{role}"])))
        html = render_template(
            "admin/schedules/list_schedules.html",
            schedules_by_specialist={},
            date_filter=None,
            today=today,
            tomorrow=today + timedelta(days=1),
        )

    empty = _soup(html).select_one(".empty-state")
    assert empty.select_one(".empty-state-title").get_text() == "Ainda não existem profissionais cadastrados"
    link = empty.select_one("a.btn")
    assert (link is not None) is has_link
    if link is not None:
        assert link["href"] == "/specialists-manager/specialists" and link.get_text() == "Ir para Profissionais"


def test_booking_form_has_the_card_fields_and_the_way_back(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check the booking page: patient, date and time, professional, labels, token and the cancel link.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    soup = _soup(client_admin.get(_url(app, "schedules.schedule_action")).get_data(as_text=True))

    assert soup.select_one("h1.page-header-title").get_text() == "Agendar consulta"
    assert soup.select_one(".page-header-back")["href"] == _url(app, "schedules.list_schedules")
    form = soup.select_one(".card form.add-schedule-form")
    assert form["method"] == "post" and form["action"] == _url(app, "schedules.schedule_action")
    assert form.select_one("input[type=hidden][name=csrf_token]") is not None
    patient = form.select_one("select[name=patient_id]")
    assert patient.has_attr("required") and form.select_one("label[for='%s']" % patient["id"]).get_text() == "Paciente"
    assert [option["value"] for option in patient.select("option[value]:not([value=''])")] == [
        str(seed["patient_nutritionist"]),
        str(seed["patient_schedule"]),
        str(seed["patient_other"]),
    ]
    moment = form.select_one("input[name=date_time]")
    assert moment["type"] == "datetime-local" and moment.has_attr("required")
    assert form.select_one("label[for='%s']" % moment["id"]).get_text() == "Data e hora"
    specialist = form.select_one("select[name=specialist]")
    assert (
        specialist.has_attr("required")
        and form.select_one("label[for='%s']" % specialist["id"]).get_text() == "Profissional"
    )
    assert [option["value"] for option in specialist.select("option[value]:not([value=''])")] == [
        NUTRITIONIST_USERNAME,
        OTHER_SPECIALIST,
    ]
    assert form.select_one("button[type=submit]").get_text(strip=True) == "Agendar consulta"
    cancel = form.select_one("a.btn-outline-secondary")
    assert cancel["href"] == _url(app, "schedules.list_schedules") and cancel.get_text() == "Cancelar"
    assert soup.select_one("script[src$='js/schedule_form.js']") is not None


def test_booking_form_of_the_nutritionist_lists_only_their_patients(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check that the nutritionist can only pick patients of their own professional record.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as the nutritionist.
    """
    soup = _soup(client_nutritionist.get(_url(app, "schedules.schedule_action")).get_data(as_text=True))

    values = [option["value"] for option in soup.select("select[name=patient_id] option[value]:not([value=''])")]
    assert values == [str(seed["patient_nutritionist"])]


def test_booking_form_without_professionals_keeps_a_text_field_and_warns(app: Flask, seed: SeedData) -> None:
    """Check the booking page of a clinic without registered professionals: a warning and a free text field.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context("/"):
        login_user(db.session.get(User, int(seed["user_admin"])))
        html = render_template("admin/schedules/schedule_action.html", patients=[], specialists=[])

    soup = _soup(html)
    assert "Ainda não existem profissionais cadastrados." in soup.select_one(".alert").get_text()
    field = soup.select_one("input[name=specialist]")
    assert field["type"] == "text" and field.has_attr("required")
    assert soup.select_one("label[for='%s']" % field["id"]) is not None
    assert soup.select_one(".alert a")["href"] == "/specialists-manager/specialists/add"


def _form(seed: SeedData, **changes: str | None) -> dict[str, str]:
    """Build a valid booking form and apply changes; a None value removes the field.

    :param seed: Ids of the fake records.
    :param changes: Fields to replace or, with None, to remove.
    :return: The form fields.
    """
    form = {
        "patient_id": str(seed["patient_schedule"]),
        "date_time": "2041-06-07T23:45",
        "specialist": NUTRITIONIST_USERNAME,
    }
    for key, value in changes.items():
        if value is None:
            form.pop(key, None)
        else:
            form[key] = value
    return form


@pytest.mark.parametrize(
    "changes, message",
    [
        pytest.param({"patient_id": None}, NO_PATIENT, id="patient-missing"),
        pytest.param({"patient_id": "   "}, NO_PATIENT, id="patient-blank"),
        pytest.param({"patient_id": "999999"}, UNKNOWN_PATIENT, id="patient-unknown"),
        pytest.param({"patient_id": "abc"}, UNKNOWN_PATIENT, id="patient-text"),
        pytest.param({"patient_id": "-3"}, UNKNOWN_PATIENT, id="patient-negative"),
        pytest.param({"specialist": None}, NO_SPECIALIST, id="professional-missing"),
        pytest.param({"specialist": "  "}, NO_SPECIALIST, id="professional-blank"),
        pytest.param({"date_time": None}, BAD_TIME, id="time-missing"),
        pytest.param({"date_time": ""}, BAD_TIME, id="time-empty"),
        pytest.param({"date_time": "amanhã"}, BAD_TIME, id="time-text"),
        pytest.param({"date_time": "2041-02-30T10:00"}, BAD_TIME, id="time-impossible-day"),
        pytest.param({"date_time": "2041-06-07"}, BAD_TIME, id="time-without-hour"),
        pytest.param({"date_time": "07/06/2041 10:00"}, BAD_TIME, id="time-brazilian-format"),
    ],
)
def test_a_bad_booking_flashes_a_message_goes_back_and_stores_nothing(
    app: Flask, seed: SeedData, client_for: ClientFactory, changes: dict[str, str | None], message: str
) -> None:
    """Check that a missing or unknown patient, a missing professional or a bad time never reach a 500.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param changes: Changes applied to the valid form.
    :param message: Message expected in the flash.
    """
    client = client_for("admin")
    before = _count(app)

    response = client.post(_url(app, "schedules.schedule_action"), data=_form(seed, **changes))

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == _url(app, "schedules.schedule_action")
    assert ("danger", message) in _flashes(client)
    assert _count(app) == before


def test_a_valid_booking_keeps_the_time_exactly_as_typed(app: Flask, seed: SeedData, client_for: ClientFactory) -> None:
    """Check that the booking is stored with the typed time, without a time zone conversion, and answers as before.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    """
    client = client_for("secretary")
    try:
        response = client.post(_url(app, "schedules.schedule_action"), data=_form(seed))

        assert response.status_code == 302
        assert urlparse(response.headers["Location"]).path == _url(app, "schedules.list_schedules")
        with app.app_context():
            visit = Schedules.query.filter_by(date_time=datetime(2041, 6, 7, 23, 45)).one()
            assert (visit.patient_id, visit.specialist, visit.status) == (
                int(seed["patient_schedule"]),
                NUTRITIONIST_USERNAME,
                "pendente",
            )
        assert (
            "message",
            f"Consulta para 'Paciente Teste 2' agendada com o profissional '{NUTRITIONIST_USERNAME}' com sucesso!",
        ) in _flashes(client)
    finally:
        with app.app_context():
            Schedules.query.filter_by(date_time=datetime(2041, 6, 7, 23, 45)).delete(synchronize_session=False)
            db.session.commit()


def test_a_professional_name_with_a_trailing_space_is_booked_and_listed_under_that_exact_name(
    app: Flask, seed: SeedData, client_for: ClientFactory
) -> None:
    """Check that the name of the professional is never trimmed: the visit is stored, listed and checked as saved.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    """
    name = "Prof Espaço "
    client = client_for("admin")
    with app.app_context():
        professional = Specialists(
            name=name, cpf="000.000.000-77", tel_number="(31) 90000-0077", email="espaco@test.local"
        )
        db.session.add(professional)
        db.session.commit()
        professional_id = professional.id
    try:
        response = client.post(
            _url(app, "schedules.schedule_action"), data=_form(seed, date_time="2042-03-04T10:00", specialist=name)
        )

        assert response.status_code == 302
        assert urlparse(response.headers["Location"]).path == _url(app, "schedules.list_schedules")
        with app.app_context():
            assert [visit.specialist for visit in Schedules.query.filter_by(date_time=datetime(2042, 3, 4, 10, 0))] == [
                name
            ]
        assert len(_card(_agenda(client, app), name).select("tbody tr")) == 1

        before = _count(app)
        nearby = client.post(
            _url(app, "schedules.schedule_action"),
            data=_form(seed, date_time="2042-03-04T10:05", specialist=name, patient_id=str(seed["patient_other"])),
        )

        assert nearby.status_code == 302
        assert urlparse(nearby.headers["Location"]).path == _url(app, "schedules.schedule_action")
        assert any(message.startswith(CONFLICT) for _, message in _flashes(client))
        assert _count(app) == before
    finally:
        with app.app_context():
            Schedules.query.filter(Schedules.specialist == name).delete(synchronize_session=False)
            Specialists.query.filter_by(id=professional_id).delete(synchronize_session=False)
            db.session.commit()


def test_a_conflicting_booking_keeps_its_message_and_suggestions(
    app: Flask, seed: SeedData, client_for: ClientFactory
) -> None:
    """Check that a visit close to another one of the professional is refused with the same text and suggestions.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    """
    client = client_for("admin")
    day = datetime.strptime(str(seed["schedule_future_date"]), "%Y-%m-%d")
    before = _count(app)

    response = client.post(
        _url(app, "schedules.schedule_action"),
        data=_form(seed, date_time=f"{seed['schedule_future_date']}T10:00", patient_id=str(seed["patient_other"])),
    )

    expected = ", ".join(
        day.replace(hour=hour, minute=minute).strftime("%d/%m/%Y %H:%M")
        for hour, minute in ((9, 0), (9, 10), (9, 20), (10, 40), (10, 50), (11, 0))
    )
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == _url(app, "schedules.schedule_action")
    assert ("message", CONFLICT + expected) in _flashes(client)
    assert _count(app) == before


def test_the_nutritionist_can_still_book_for_the_own_professional(
    app: Flask, seed: SeedData, client_nutritionist: FlaskClient
) -> None:
    """Check that the booking of the nutritionist is stored, so the robustness rules did not change their access.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_nutritionist: Test client logged in as the nutritionist.
    """
    when = datetime(2041, 7, 8, 7, 30)
    try:
        response = client_nutritionist.post(
            _url(app, "schedules.schedule_action"),
            data=_form(seed, date_time="2041-07-08T07:30", patient_id=str(seed["patient_nutritionist"])),
        )

        assert response.status_code == 302
        with app.app_context():
            assert Schedules.query.filter_by(date_time=when, specialist=NUTRITIONIST_USERNAME).count() == 1
    finally:
        with app.app_context():
            Schedules.query.filter_by(date_time=when).delete(synchronize_session=False)
            db.session.commit()


def test_visits_of_past_days_are_still_finished_when_the_agenda_opens(
    app: Flask, seed: SeedData, client_admin: FlaskClient
) -> None:
    """Check that the agenda keeps updating the pending visits of earlier clinic days to finished.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_admin: Test client logged in as admin.
    """
    with app.app_context():
        visit = Schedules(
            patient_id=int(seed["patient_other"]),
            date_time=datetime.now() - timedelta(days=400),
            specialist=OTHER_SPECIALIST,
            status="pendente",
        )
        db.session.add(visit)
        db.session.commit()
        visit_id = visit.id
    try:
        client_admin.get(_url(app, "schedules.list_schedules"))

        with app.app_context():
            assert db.session.get(Schedules, visit_id).status == "finalizado"
    finally:
        with app.app_context():
            Schedules.query.filter_by(id=visit_id).delete(synchronize_session=False)
            db.session.commit()


def test_the_helpers_of_the_booking_form(app: Flask) -> None:
    """Check the two small helpers of the booking view.

    :param app: Flask application.
    """
    from app.views.schedules import find_patient, parse_visit_time

    assert parse_visit_time("2041-06-07T23:45") == datetime(2041, 6, 7, 23, 45)
    assert parse_visit_time("2041-06-07 23:45") is None
    with app.app_context():
        assert find_patient("abc") is None and find_patient("") is None and find_patient("0") is None
