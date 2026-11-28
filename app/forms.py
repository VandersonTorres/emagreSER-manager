import re
from typing import Any

from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import (
    DateField,
    FileField,
    FloatField,
    Form,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
)
from wtforms.validators import DataRequired, InputRequired, Length, Optional, Regexp, ValidationError

from app.models import Diet, Specialists, User

MESSAGES_PT_BR: dict[str, str] = {
    "Invalid field name '%s'.": "Nome de campo inválido: '%s'.",
    "Field must be equal to %(other_name)s.": "O campo deve ser igual a %(other_name)s.",
    "Field must be between %(min)d and %(max)d characters long.": (
        "O campo deve ter entre %(min)d e %(max)d caracteres."
    ),
    "Number must be at least %(min)s.": "O número deve ser no mínimo %(min)s.",
    "Number must be at most %(max)s.": "O número deve ser no máximo %(max)s.",
    "Number must be between %(min)s and %(max)s.": "O número deve estar entre %(min)s e %(max)s.",
    "This field is required.": "Este campo é obrigatório.",
    "Invalid input.": "Valor inválido.",
    "Invalid email address.": "Endereço de e-mail inválido.",
    "Invalid IP address.": "Endereço IP inválido.",
    "Invalid Mac address.": "Endereço MAC inválido.",
    "Invalid URL.": "Endereço da internet (URL) inválido.",
    "Invalid UUID.": "Identificador (UUID) inválido.",
    "Invalid value, must be one of: %(values)s.": "Valor inválido; use um destes: %(values)s.",
    "Invalid value, can't be any of: %(values)s.": "Valor inválido; não pode ser nenhum destes: %(values)s.",
    "This field cannot be edited.": "Este campo não pode ser editado.",
    "This field is disabled and cannot have a value.": "Este campo está desativado e não pode ter valor.",
    "Invalid CSRF Token.": "Token de segurança (CSRF) inválido.",
    "CSRF token missing.": "Token de segurança (CSRF) ausente.",
    "CSRF failed.": "Falha na verificação de segurança (CSRF).",
    "CSRF token expired.": "Token de segurança (CSRF) expirado.",
    "Invalid Choice: could not coerce.": "Opção inválida: não foi possível interpretar o valor.",
    "Choices cannot be None.": "As opções não podem ser nulas.",
    "Not a valid choice.": "Selecione uma opção válida.",
    "Invalid choice(s): one or more data inputs could not be coerced.": (
        "Opções inválidas: um ou mais valores não puderam ser interpretados."
    ),
    "Not a valid datetime value.": "Informe uma data e hora válidas.",
    "Not a valid date value.": "Informe uma data válida.",
    "Not a valid time value.": "Informe uma hora válida.",
    "Not a valid week value.": "Informe uma semana válida.",
    "Not a valid integer value.": "Informe um número inteiro válido.",
    "Not a valid decimal value.": "Informe um número decimal válido.",
    "Not a valid float value.": "Informe um número válido.",
}

PLURAL_MESSAGES_PT_BR: dict[str, tuple[str, str]] = {
    "Field must be at least %(min)d character long.": (
        "O campo deve ter pelo menos %(min)d caractere.",
        "O campo deve ter pelo menos %(min)d caracteres.",
    ),
    "Field cannot be longer than %(max)d character.": (
        "O campo não pode ter mais de %(max)d caractere.",
        "O campo não pode ter mais de %(max)d caracteres.",
    ),
    "Field must be exactly %(max)d character long.": (
        "O campo deve ter exatamente %(max)d caractere.",
        "O campo deve ter exatamente %(max)d caracteres.",
    ),
    "'%(value)s' is not a valid choice for this field.": (
        "'%(value)s' não é uma opção válida para este campo.",
        "'%(value)s' não são opções válidas para este campo.",
    ),
}


class PortugueseTranslations:
    """Brazilian Portuguese translations of the WTForms messages, written in the app.

    The ``pt`` catalog shipped with WTForms is the Portuguese from Portugal and has odd phrases, so it is not used. A
    message that is not in the catalogs, such as a custom one, is returned unchanged.
    """

    def gettext(self, string: str) -> str:
        """Translate a message.

        :param string: The English message of WTForms.
        :return: The Brazilian Portuguese message, or ``string`` when it has no translation.
        """
        return MESSAGES_PT_BR.get(string, string)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        """Translate a message that depends on a number; in Brazilian Portuguese only values above one are plural.

        :param singular: The English message for one.
        :param plural: The English message for other numbers.
        :param n: The number that selects the form.
        :return: The Brazilian Portuguese message, or the English one when it has no translation.
        """
        forms = PLURAL_MESSAGES_PT_BR.get(singular)
        if forms is None:
            return singular if n == 1 else plural
        return forms[1] if n > 1 else forms[0]


PORTUGUESE_TRANSLATIONS = PortugueseTranslations()

OBSERVATION_MAX_LENGTH = 1000
USER_TEXT_MAX_LENGTH = 255
USER_ROLES: tuple[tuple[str, str], ...] = (
    ("admin", "Gestor"),
    ("secretary", "Secretária"),
    ("nutritionist", "Nutricionista"),
)
USER_ROLE_LABELS: dict[str, str] = dict(USER_ROLES)
PASSWORD_REQUIREMENTS = (
    "pelo menos 6 caracteres, com letra minúscula, letra maiúscula, número e símbolo"  # pragma: allowlist secret
)
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{6,}\Z", re.ASCII)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+\Z")


def clean_observation(value: str | None) -> str | None:
    """Prepare the text of an observation for storage: browser line breaks become ``\\n``, the ends are stripped.

    The browser counts a line break as one character in ``maxlength`` but sends two, so the breaks are normalized
    before the length is validated. A blank text becomes ``None``, which clears the observation of the measurement.

    :param value: Text typed in the field, or ``None`` when the field was not sent.
    :return: The text without surrounding blanks, or ``None`` when nothing but blanks was typed.
    """
    if value is None:
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None


def strip_text(value: str | None) -> str | None:
    """Remove the blanks around a typed text.

    :param value: Text typed in the field, or ``None`` when the field was not sent.
    :return: The text without surrounding blanks, or ``None`` when the field was not sent.
    """
    return value.strip() if isinstance(value, str) else value


class AppForm(FlaskForm):
    """Base of every form of the app: a Flask-WTF form whose validation messages are in Brazilian Portuguese."""

    class Meta:
        """Form options; the translations of the app win over the ones of Flask-WTF."""

        def get_translations(self, form: Form) -> PortugueseTranslations:
            """Provide the translations used by the fields and validators of the form.

            :param form: The form being built.
            :return: The Brazilian Portuguese translations.
            """
            return PORTUGUESE_TRANSLATIONS


class SpecialistForm(AppForm):
    """Form to create or edit a specialist."""

    name = StringField("Nome do Profissional", validators=[DataRequired()])
    cpf = StringField("CPF", validators=[DataRequired()])
    tel_number = StringField("Telefone", validators=[DataRequired()])
    email = StringField("E-mail", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class UserForm(AppForm):
    """Form to create a user account, with a name, an e-mail, a password and one of the three roles.

    The e-mail must not be registered yet, whatever the letter case, and the name must be free as well, because both
    are unique in the database. The password is never sent back to the page.
    """

    name = StringField(
        "Nome",
        validators=[DataRequired(message="Informe o nome do usuário."), Length(max=USER_TEXT_MAX_LENGTH)],
        filters=[strip_text],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe o e-mail do usuário."), Length(max=USER_TEXT_MAX_LENGTH)],
        filters=[strip_text],
    )
    password = PasswordField(
        "Senha",
        validators=[
            DataRequired(message="Informe a senha."),
            Regexp(PASSWORD_PATTERN, message=f"A senha deve ter {PASSWORD_REQUIREMENTS}."),
        ],
        description=f"Use {PASSWORD_REQUIREMENTS}.",
    )
    role = RadioField(
        "Função", choices=list(USER_ROLES), validators=[DataRequired(message="Escolha a função do usuário.")]
    )

    submit = SubmitField("Cadastrar usuário")

    def validate_name(self, field: StringField) -> None:
        """Refuse a name that another user already has.

        :param field: The name field.
        :raises ValidationError: If a user with the same name exists.
        """
        if User.query.filter(User.username == field.data).first() is not None:
            raise ValidationError("Já existe um usuário com este nome. Use outro nome.")

    def validate_email(self, field: StringField) -> None:
        """Refuse an e-mail with a wrong format or one that is already registered, whatever the letter case.

        :param field: The e-mail field.
        :raises ValidationError: If the format is wrong or a user with the same e-mail exists.
        """
        if EMAIL_PATTERN.fullmatch(field.data) is None:
            raise ValidationError("Informe um e-mail válido, como nome@exemplo.com.")
        if User.query.filter(func.lower(User.email) == field.data.lower()).first() is not None:
            raise ValidationError("Já existe um usuário cadastrado com este e-mail.")


class PatientForm(AppForm):
    """Form to create or edit a patient, with the personal, clinical and behavioral history."""

    name = StringField("Nome", validators=[DataRequired()])
    gender = SelectField(
        "Sexo",
        choices=[("", "Selecione"), ("masculino", "Masculino"), ("feminino", "Feminino")],
        validators=[DataRequired()],
    )
    birth_date = DateField("Data de nascimento", format="%Y-%m-%d", validators=[DataRequired()])
    cpf = StringField("CPF", validators=[Optional()])
    tel_number = StringField("Telefone", validators=[DataRequired()])
    email = StringField("E-mail", validators=[Optional()])
    specialist_id = SelectField("Profissional", coerce=int, validators=[DataRequired()])

    medication = SelectField(
        "Faz uso de medicação?",
        choices=[("", "Selecione"), ("não", "Não"), ("sim", "Sim")],
        validators=[DataRequired()],
    )
    medications_details = StringField("Se sim, quais?", validators=[Optional()])
    intestine = IntegerField("Funcionamento intestinal (vezes por semana)", validators=[DataRequired()])
    allergies = SelectField(
        "Alergias / intolerâncias?",
        choices=[("", "Selecione"), ("não", "Não"), ("sim", "Sim")],
        validators=[DataRequired()],
    )
    allergies_details = StringField("Se sim, quais?", validators=[Optional()])
    water = FloatField("Litros de água por dia", validators=[DataRequired()])

    physical_activities = SelectField(
        "Faz atividade física?",
        choices=[("", "Selecione"), ("não", "Não"), ("sim", "Sim")],
        validators=[DataRequired()],
    )
    physical_details = StringField("Se sim, quais?", validators=[Optional()])
    hours = TimeField("Horário das atividades", validators=[Optional()])
    frequency = IntegerField("Frequência das atividades (vezes por semana)", validators=[Optional()])
    objective = StringField("Objetivo da consulta", validators=[DataRequired()])

    submit = SubmitField("Salvar")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the form and fill the specialist choices from the database.

        :param args: Positional arguments of ``AppForm``.
        :param kwargs: Keyword arguments of ``AppForm``.
        """
        super().__init__(*args, **kwargs)
        self.specialist_id.choices = [(s.id, s.name) for s in Specialists.query.all()]


class AnthropometricAssessmentForm(AppForm):
    """Form of an anthropometric evaluation of a patient."""

    data_avaliacao = DateField("Data de Avaliação", format="%Y-%m-%d", validators=[DataRequired()])
    ultima_guia = StringField("Nome da Guia", validators=[DataRequired()])
    idade = IntegerField("Idade", validators=[DataRequired()])
    evolucao = StringField("Evolução", validators=[Optional()])
    p_max = FloatField("Peso Máximo", validators=[DataRequired()])
    p_ide = FloatField("Peso Ideal", validators=[DataRequired()])
    p_min = FloatField("Peso Mínimo", validators=[DataRequired()])
    imc = FloatField("IMC", validators=[DataRequired()])
    nutri_class = StringField("Classificação Nutricional", validators=[DataRequired()])
    necessidade_calorica = StringField("Necessidade Calórica", validators=[Optional()])
    ingestao_liquido = FloatField("Ingestão de Líquido", validators=[DataRequired()])
    grau_atv_fisica = SelectField(
        "Grau de Atividade Física",
        choices=[
            ("", "Selecione"),
            ("Pouco Ativa", "Pouco Ativa"),
            ("Moderado", "Moderadamente Ativa"),
            ("Muito Ativa", "Muito Ativa"),
        ],
        validators=[DataRequired()],
    )

    submit = SubmitField("Salvar")


class SkinfoldMeasurementForm(AppForm):
    """Form of a skinfold measurement of a patient."""

    data_medicao = DateField("Data de Medição", format="%Y-%m-%d", validators=[DataRequired()])
    altura = FloatField("Altura (m)", validators=[DataRequired()])
    peso = FloatField("Peso (kg)", validators=[InputRequired()])
    massa_muscular = FloatField("Massa Muscular", validators=[InputRequired()])
    gordura = FloatField("Gordura", validators=[InputRequired()])
    abdominal = FloatField("Abdominal", validators=[InputRequired()])
    cintura = FloatField("Cintura", validators=[InputRequired()])
    quadril = FloatField("Quadril", validators=[InputRequired()])
    idade_metabolica = IntegerField("Idade Metabólica", validators=[InputRequired()])
    pa = StringField("Pressão Arterial", validators=[InputRequired()])
    observacoes = TextAreaField(
        "Observações", validators=[Optional(), Length(max=OBSERVATION_MAX_LENGTH)], filters=[clean_observation]
    )

    submit = SubmitField("Salvar")


class DietForm(AppForm):
    """Form to create or edit a diet, with the fixed names and the ones already saved."""

    name = SelectField("Nome da Dieta", validators=[DataRequired()])
    other_name = StringField("Outro (especifique)", validators=[Optional()])
    description = TextAreaField("Descrição", validators=[Optional()])
    diet_file = FileField("Arquivo da Dieta", validators=[Optional()])
    submit = SubmitField("Salvar")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the form and fill the name choices with the fixed names, the saved ones and "Outro".

        :param args: Positional arguments of ``AppForm``.
        :param kwargs: Keyword arguments of ``AppForm``.
        """
        super(DietForm, self).__init__(*args, **kwargs)
        fixed_choices = [
            ("Dieta Cetogênica", "Dieta Cetogênica"),
            ("Dieta Low Carb I", "Dieta Low Carb I"),
            ("Dieta Low Carb II", "Dieta Low Carb II"),
            ("Dieta Low Carb III", "Dieta Low Carb III"),
            ("Dieta Termogênico N3", "Dieta Termogênico N3"),
            ("Dieta Guia N2", "Dieta Guia N2"),
            ("Dieta Guia N5", "Dieta Guia N5"),
            ("Dieta Detox", "Dieta Detox"),
            ("Dieta Violeta", "Dieta Violeta"),
            ("Dieta Laxativa", "Dieta Laxativa"),
            ("Dieta Primavera", "Dieta Primavera"),
            ("Dieta Zero Açucar", "Dieta Zero Açucar"),
        ]
        extra_choices = [
            (diet.name, diet.name)
            for diet in Diet.query.all()
            if diet.name.lower() not in [choice[0].lower() for choice in fixed_choices]
        ]
        self.name.choices = fixed_choices + extra_choices + [("Outro", "Outro")]


class BackupForm(AppForm):
    """Empty form that carries only the CSRF token of the backup download."""
