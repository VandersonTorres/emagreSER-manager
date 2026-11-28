"""Validation messages in Brazilian Portuguese: the catalog covers WTForms, forms and pages use it, and CSRF is kept."""

import ast
import inspect
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import wtforms
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectMultipleField, StringField
from wtforms.validators import Length, NumberRange, Optional

from app import forms
from app.forms import (
    MESSAGES_PT_BR,
    PLURAL_MESSAGES_PT_BR,
    PORTUGUESE_TRANSLATIONS,
    AnthropometricAssessmentForm,
    AppForm,
    PatientForm,
    SkinfoldMeasurementForm,
)
from app.models import AnthropometricEvaluation, Diet, SkinFolds, db
from tests.aliases import SeedData
from tests.form_helpers import form_entries
from tests.test_csrf_rendering import CSRF_MESSAGE, csrf_on  # noqa: F401

POT_PATH = Path(wtforms.__file__).parent / "locale" / "wtforms.pot"
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]|%[sd]")
REQUIRED = "Este campo é obrigatório."
FLOAT = "Informe um número válido."
INTEGER = "Informe um número inteiro válido."
DATE = "Informe uma data válida."
CHOICE = "Selecione uma opção válida."


class SampleForm(AppForm):
    """Form with the validators and fields of WTForms that the patient forms do not use."""

    text = StringField("Texto", validators=[Optional(), Length(min=3, max=5)])
    exact = StringField("Exato", validators=[Optional(), Length(min=1, max=1)])
    number = IntegerField("Número", validators=[Optional(), NumberRange(min=1, max=10)])
    tags = SelectMultipleField("Etiquetas", choices=[("a", "A")])


def _read_literal(text: str) -> str:
    """Read the quoted string of a catalog line.

    :param text: The line without its keyword, such as ``"Invalid input."``.
    :return: The string with its escapes resolved.
    """
    return ast.literal_eval(text.strip())


def _pot_messages() -> list[tuple[str, str | None]]:
    """Read every message of the WTForms template catalog of the installed version, without the header.

    :return: The (msgid, msgid_plural) pairs; the plural is None for messages without one.
    """
    entries: list[dict[str, str]] = []
    target: str | None = None
    for line in POT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("msgid_plural "):
            target = "plural"
            entries[-1][target] = _read_literal(stripped.removeprefix("msgid_plural "))
        elif stripped.startswith("msgid "):
            target = "id"
            entries.append({target: _read_literal(stripped.removeprefix("msgid "))})
        elif stripped.startswith("msgstr"):
            target = None
        elif stripped.startswith('"') and target:
            entries[-1][target] += _read_literal(stripped)
    return [(entry["id"], entry.get("plural")) for entry in entries if entry["id"]]


def _placeholders(text: str) -> list[str]:
    """List the ``%`` placeholders of a message, sorted.

    :param text: The message.
    :return: The placeholders, such as ``%(min)d``.
    """
    return sorted(PLACEHOLDER.findall(text))


def test_the_installed_catalog_is_read() -> None:
    """Check the catalog reader: the messages with and without plural of WTForms are found."""
    messages = dict(_pot_messages())

    assert "This field is required." in messages and messages["This field is required."] is None
    assert messages["Field must be at least %(min)d character long."] == (
        "Field must be at least %(min)d characters long."
    )
    assert len(messages) >= 30


def test_translations_cover_every_message_of_the_installed_wtforms() -> None:
    """Check that no message of the installed WTForms is left in English, so an upgrade with new ones fails here.

    Each translation must differ from the English text and keep the same placeholders; the plural messages must have
    a singular form for one and a plural form for the other numbers.
    """
    missing: list[str] = []
    for message_id, plural in _pot_messages():
        if plural is None:
            translated = PORTUGUESE_TRANSLATIONS.gettext(message_id)
            if translated == message_id or _placeholders(translated) != _placeholders(message_id):
                missing.append(message_id)
            continue
        one = PORTUGUESE_TRANSLATIONS.ngettext(message_id, plural, 1)
        many = PORTUGUESE_TRANSLATIONS.ngettext(message_id, plural, 2)
        if (
            one in (message_id, plural)
            or many in (message_id, plural)
            or one == many
            or _placeholders(one) != _placeholders(message_id)
            or _placeholders(many) != _placeholders(plural)
        ):
            missing.append(message_id)
    assert missing == []


def test_the_catalog_has_no_message_that_wtforms_no_longer_has() -> None:
    """Check that every message of the app catalog still exists in the installed WTForms, so the catalog stays tidy."""
    ids = {message_id for message_id, _ in _pot_messages()}

    assert set(MESSAGES_PT_BR) | set(PLURAL_MESSAGES_PT_BR) == ids
    assert not set(MESSAGES_PT_BR) & set(PLURAL_MESSAGES_PT_BR)


def test_the_catalog_is_brazilian_portuguese_and_not_the_portugal_one() -> None:
    """Check some phrases: the app wording is used and the odd phrases of the catalog shipped with WTForms are not."""
    every_text = " ".join(
        [*MESSAGES_PT_BR.values(), *(text for pair in PLURAL_MESSAGES_PT_BR.values() for text in pair)]
    )

    assert "flutuante" not in every_text and "vírgula" not in every_text
    assert MESSAGES_PT_BR["This field is required."] == REQUIRED
    assert MESSAGES_PT_BR["Not a valid float value."] == FLOAT
    assert MESSAGES_PT_BR["Not a valid integer value."] == INTEGER
    assert MESSAGES_PT_BR["Not a valid date value."] == DATE
    assert MESSAGES_PT_BR["Not a valid choice."] == CHOICE


def test_unknown_messages_are_returned_unchanged() -> None:
    """Check the fallback: custom messages and labels that are not in the catalog keep their text."""
    assert PORTUGUESE_TRANSLATIONS.gettext("Csrf Token") == "Csrf Token"
    assert PORTUGUESE_TRANSLATIONS.ngettext("one thing", "many things", 1) == "one thing"
    assert PORTUGUESE_TRANSLATIONS.ngettext("one thing", "many things", 3) == "many things"


@pytest.mark.parametrize("count, expected", [(0, "caractere."), (1, "caractere."), (2, "caracteres.")])
def test_plural_follows_the_brazilian_rule(count: int, expected: str) -> None:
    """Check that zero and one take the singular and only larger numbers take the plural.

    :param count: Number that selects the form.
    :param expected: Ending of the message.
    """
    text = PORTUGUESE_TRANSLATIONS.ngettext(
        "Field must be at least %(min)d character long.", "Field must be at least %(min)d characters long.", count
    )

    assert text.endswith(expected)


def test_every_form_of_the_app_derives_from_the_base_form_and_uses_its_translations(app: Flask) -> None:
    """Check that no form of app/forms.py is left on the English messages of Flask-WTF.

    :param app: Flask application.
    """
    classes = [
        cls
        for _, cls in inspect.getmembers(forms, inspect.isclass)
        if issubclass(cls, FlaskForm) and cls is not FlaskForm and cls.__module__ == forms.__name__
    ]

    assert {cls.__name__ for cls in classes} >= {
        "AppForm",
        "SpecialistForm",
        "PatientForm",
        "AnthropometricAssessmentForm",
        "SkinfoldMeasurementForm",
        "DietForm",
        "BackupForm",
    }
    with app.test_request_context():
        for cls in classes:
            assert issubclass(cls, AppForm), cls.__name__
            form = cls()
            assert form.meta.get_translations(form) is PORTUGUESE_TRANSLATIONS, cls.__name__


def _post(app: Flask, form_class: type[FlaskForm], data: dict[str, str]) -> FlaskForm:
    """Validate a form built from a posted request.

    :param app: Flask application.
    :param form_class: Form to build.
    :param data: Posted values.
    :return: The validated form; the request context is closed, so only the data of the form can be read.
    """
    with app.test_request_context("/", method="POST", data=data):
        form = form_class()
        form.validate()
        return form


def test_required_fields_of_the_patient_forms_answer_in_portuguese(app: Flask) -> None:
    """Check the required message of the three patient forms posted empty: DataRequired and InputRequired fields.

    :param app: Flask application.
    """
    patient = _post(app, PatientForm, {})
    evaluation = _post(app, AnthropometricAssessmentForm, {})
    skinfold = _post(app, SkinfoldMeasurementForm, {})

    for form, names in (
        (patient, ("name", "gender", "birth_date", "tel_number", "intestine", "water", "objective")),
        (evaluation, ("data_avaliacao", "ultima_guia", "idade", "p_max", "imc", "grau_atv_fisica")),
        (skinfold, ("data_medicao", "altura", "peso", "massa_muscular", "pa")),
    ):
        for name in names:
            assert form[name].errors == [REQUIRED], (type(form).__name__, name)


def test_number_fields_of_the_patient_forms_answer_in_portuguese(app: Flask) -> None:
    """Check the float and integer messages, which show where the field only requires that something was typed.

    :param app: Flask application.
    """
    skinfold = _post(app, SkinfoldMeasurementForm, {"peso": "abc", "gordura": "1,5x", "idade_metabolica": "1.5"})
    patient = _post(app, PatientForm, {"frequency": "muitas"})

    assert skinfold.peso.errors == [FLOAT] and skinfold.gordura.errors == [FLOAT]
    assert skinfold.idade_metabolica.errors == [INTEGER]
    assert patient.frequency.errors == [INTEGER]


def test_date_and_choice_messages_come_in_portuguese_from_the_patient_forms(app: Flask) -> None:
    """Check the date and choice messages produced by the real fields of the patient forms.

    A malformed date is reported as required by the form (DataRequired replaces the error list), but the message of
    the date field itself is the one the app translated.

    :param app: Flask application.
    """
    skinfold = _post(app, SkinfoldMeasurementForm, {"data_medicao": "31/02/2026"})
    evaluation = _post(app, AnthropometricAssessmentForm, {"data_avaliacao": "ontem", "grau_atv_fisica": "x"})
    patient = _post(app, PatientForm, {"gender": "outro", "medication": "talvez", "specialist_id": "abc"})

    assert skinfold.data_medicao.process_errors == [DATE]
    assert evaluation.data_avaliacao.process_errors == [DATE]
    assert evaluation.grau_atv_fisica.errors == [CHOICE]
    assert patient.gender.errors == [CHOICE] and patient.medication.errors == [CHOICE]
    assert patient.specialist_id.process_errors == ["Opção inválida: não foi possível interpretar o valor."]


def test_length_range_and_multiple_choice_messages_use_the_right_plural(app: Flask) -> None:
    """Check messages that depend on a number, which the patient forms do not use, through a sample form.

    :param app: Flask application.
    """
    short = _post(app, SampleForm, {"text": "a", "exact": "ab", "number": "11", "tags": ["x", "y"]})
    one_invalid = _post(app, SampleForm, {"tags": ["x"]})
    long_text = _post(app, SampleForm, {"text": "abcdef", "number": "0"})

    assert short.text.errors == ["O campo deve ter entre 3 e 5 caracteres."]
    assert short.exact.errors == ["O campo deve ter exatamente 1 caractere."]
    assert short.number.errors == ["O número deve estar entre 1 e 10."]
    assert short.tags.errors in (
        ["'x', 'y' não são opções válidas para este campo."],
        ["'y', 'x' não são opções válidas para este campo."],
    )
    assert one_invalid.tags.errors == ["'x' não é uma opção válida para este campo."]
    assert long_text.text.errors == ["O campo deve ter entre 3 e 5 caracteres."]


def _field_errors(html: str) -> list[str]:
    """List the error texts a page shows under its fields.

    :param html: HTML of the page.
    :return: The texts of the field errors, in document order.
    """
    soup = BeautifulSoup(html, "html.parser")
    return [
        item.get_text(strip=True) for item in soup.select(".invalid-feedback > div, .text-danger") if item.get_text()
    ]


def _no_english_message(html: str) -> bool:
    """Tell whether a page is free of the English messages of WTForms.

    :param html: HTML of the page.
    :return: True when none of the messages of the installed WTForms shows up in the page.
    """
    english = [
        text for message_id, plural in _pot_messages() for text in (message_id, plural) if text and "%" not in text
    ]
    return not any(text in html for text in english)


def test_a_rendered_measurement_page_shows_the_errors_in_portuguese(
    app: Flask, client_admin: FlaskClient, seed: SeedData
) -> None:
    """Check the new bioimpedance page after an invalid post: each error is next to its field, in Brazilian Portuguese.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context():
        url = url_for("patients.add_skinfold", patient_id=int(seed["patient_nutritionist"]))
    posted = {"data_medicao": "31/02/2026", "peso": "abc", "idade_metabolica": "1.5", "pa": "12/8", "gordura": "x"}

    response = client_admin.post(url, data=posted)

    html = response.get_data(as_text=True)
    soup = BeautifulSoup(html, "html.parser")
    assert response.status_code == 200
    assert soup.select_one("#peso-feedback").get_text(strip=True) == FLOAT
    assert soup.select_one("#gordura-feedback").get_text(strip=True) == FLOAT
    assert soup.select_one("#idade_metabolica-feedback").get_text(strip=True) == INTEGER
    assert soup.select_one("#data_medicao-feedback").get_text(strip=True) == REQUIRED
    assert "pa-feedback" not in html
    assert _no_english_message(html)
    assert set(_field_errors(html)) == {FLOAT, INTEGER, REQUIRED}


def test_a_rendered_evaluation_page_shows_the_errors_in_portuguese(
    app: Flask, client_admin: FlaskClient, seed: SeedData
) -> None:
    """Check the new evaluation page after an invalid post, with required fields and an invalid choice.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context():
        url = url_for("patients.add_anthro", patient_id=int(seed["patient_nutritionist"]))

    response = client_admin.post(url, data={"grau_atv_fisica": "x", "idade": "abc"})

    html = response.get_data(as_text=True)
    soup = BeautifulSoup(html, "html.parser")
    assert response.status_code == 200
    assert soup.select_one("#grau_atv_fisica-feedback").get_text(strip=True) == CHOICE
    assert soup.select_one("#idade-feedback").get_text(strip=True) == REQUIRED
    assert soup.select_one("#data_avaliacao-feedback").get_text(strip=True) == REQUIRED
    assert _no_english_message(html)


def test_the_diet_edit_page_shows_the_errors_in_portuguese(
    app: Flask, client_admin: FlaskClient, seed: SeedData
) -> None:
    """Check the raw diet edit page, which prints the errors of its own fields, after a post with an invalid name.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    """
    with app.test_request_context():
        url = url_for("diets.edit_diet_raw", id=int(seed["diet_a4"]))

    response = client_admin.post(url, data={"name": "Dieta Que Nao Existe", "description": "x"})

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert _field_errors(html) == [CHOICE]
    assert _no_english_message(html)
    with app.app_context():
        assert db.session.get(Diet, int(seed["diet_a4"])).name == "Dieta Teste A4"


def _csrf_pages(app: Flask, seed: SeedData, complete_patient: dict[str, int]) -> dict[str, tuple[str, str]]:
    """Map each validated patient form to its URL and form selector.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :return: The (URL path, form selector) of each form.
    """
    patient = int(seed["patient_nutritionist"])
    complete = complete_patient["patient"]
    with app.test_request_context():
        return {
            "add_skinfold": (url_for("patients.add_skinfold", patient_id=patient), "form.add-skinfold-form"),
            "add_anthro": (url_for("patients.add_anthro", patient_id=patient), "form.add-anthro-form"),
            "edit_skinfold": (
                url_for("patients.edit_skinfold", patient_id=complete, skinfold_id=complete_patient["skinfold"]),
                "form.edit-skinfold-form",
            ),
            "edit_anthro": (
                url_for("patients.edit_anthro", patient_id=complete, evaluation_id=complete_patient["evaluation"]),
                "form.edit-anthro-form",
            ),
        }


def _stored_counts(app: Flask, seed: SeedData, complete_patient: dict[str, int]) -> tuple[int, int, float, int]:
    """Read what the validated forms could change.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :return: The number of measurements and evaluations of the seeded patient, and the weight and age stored in the
        records the edit forms open.
    """
    with app.app_context():
        patient = int(seed["patient_nutritionist"])
        return (
            SkinFolds.query.filter_by(patient_id=patient).count(),
            AnthropometricEvaluation.query.filter_by(patient_id=patient).count(),
            db.session.get(SkinFolds, complete_patient["skinfold"]).peso,
            db.session.get(AnthropometricEvaluation, complete_patient["evaluation"]).idade,
        )


@pytest.mark.usefixtures("csrf_on")
@pytest.mark.parametrize("token", ["missing", "wrong"])
@pytest.mark.parametrize("page", ["add_skinfold", "add_anthro", "edit_skinfold", "edit_anthro"])
def test_validated_forms_still_refuse_a_post_without_a_valid_token(
    app: Flask,
    client_admin: FlaskClient,
    seed: SeedData,
    complete_patient: dict[str, int],
    page: str,
    token: str,
) -> None:
    """Check that a post without a valid CSRF token saves nothing and, back on the page, shows one message in pt-BR.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param seed: Ids of the fake records.
    :param complete_patient: Ids of the patient with every field filled and its records.
    :param page: Validated form under test.
    :param token: Whether the token is left out or replaced by a wrong one.
    """
    url, selector = _csrf_pages(app, seed, complete_patient)[page]
    html = client_admin.get(url).get_data(as_text=True)
    data = dict(form_entries(html, selector))
    assert "csrf_token" in data
    data.update(
        {"data_medicao": "2031-01-02", "data_avaliacao": "2031-01-02", "peso": "99.5", "idade": "77", "pa": "12/8"}
    )
    if token == "missing":
        del data["csrf_token"]
    else:
        data["csrf_token"] = "not-a-valid-token"
    before = _stored_counts(app, seed, complete_patient)

    response = client_admin.post(url, data=data, headers={"Referer": f"http://localhost{url}"})

    assert response.status_code == 302
    assert response.headers["Location"] == f"http://localhost{url}"
    body = client_admin.get(url).get_data(as_text=True)
    toasts = [toast.get_text() for toast in BeautifulSoup(body, "html.parser").select("#toast-region .toast-body")]
    assert len(toasts) == 1 and CSRF_MESSAGE in toasts[0]
    assert "The CSRF" not in body and "CSRF token" not in body
    assert _stored_counts(app, seed, complete_patient) == before


@pytest.mark.usefixtures("csrf_on")
def test_a_valid_token_is_still_accepted_and_the_form_renders_without_alert(
    app: Flask, client_admin: FlaskClient, case_patients: Callable[..., int]
) -> None:
    """Check that the token rendered in the page is accepted: the measurement is saved and there is no CSRF message.

    :param app: Flask application.
    :param client_admin: Test client logged in as admin.
    :param case_patients: Factory of temporary patients.
    """
    patient_id = case_patients("Paciente Csrf Valido")
    with app.test_request_context():
        url = url_for("patients.add_skinfold", patient_id=patient_id)
    html = client_admin.get(url).get_data(as_text=True)
    assert CSRF_MESSAGE not in html
    data: dict[str, Any] = dict(form_entries(html, "form.add-skinfold-form"))
    data.update({"data_medicao": "2031-01-02", "altura": "1.7", "peso": "70.5", "pa": "12/8"})

    response = client_admin.post(url, data=data)

    assert response.status_code == 302
    with app.app_context():
        assert SkinFolds.query.filter_by(patient_id=patient_id).count() == 1
