from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FileField,
    FloatField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
)
from wtforms.validators import DataRequired, Optional

from app.models import Diet, Specialists


class SpecialistForm(FlaskForm):
    name = StringField("Nome do Profissional", validators=[DataRequired()])
    cpf = StringField("CPF", validators=[DataRequired()])
    tel_number = StringField("Telefone", validators=[DataRequired()])
    email = StringField("E-mail", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class PatientForm(FlaskForm):
    # Dados pessoais
    name = StringField("Nome", validators=[DataRequired()])
    gender = SelectField(
        "Sexo",
        choices=[("", "Selecione"), ("masculino", "Masculino"), ("feminino", "Feminino")],
        validators=[DataRequired()],
    )
    birth_date = DateField("Data de nascimento", format="%Y-%m-%d", validators=[DataRequired()])
    cpf = StringField("CPF", validators=[DataRequired()])
    tel_number = StringField("Telefone", validators=[DataRequired()])
    email = StringField("E-mail", validators=[DataRequired()])
    specialist_id = SelectField("Profissional", coerce=int, validators=[DataRequired()])

    # História Clínica
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
    heartburn = SelectField(
        "Azia / Refluxo", choices=[("", "Selecione"), ("não", "Não"), ("sim", "Sim")], validators=[DataRequired()]
    )

    # História Comportamental
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.specialist_id.choices = [(s.id, s.name) for s in Specialists.query.all()]


class AnthropometricAssessmentForm(FlaskForm):
    data_avaliacao = DateField("Data de Avaliação", format="%Y-%m-%d", validators=[DataRequired()])
    ultima_guia = StringField("Nome da Guia", validators=[DataRequired()])
    idade = IntegerField("Idade", validators=[DataRequired()])
    altura = FloatField("Altura (m)", validators=[DataRequired()])
    peso = FloatField("Peso (kg)", validators=[DataRequired()])
    evolucao = StringField("Evolução", validators=[Optional()])
    p_max = FloatField("Peso Máximo", validators=[DataRequired()])
    p_ide = FloatField("Peso Ideal", validators=[DataRequired()])
    p_min = FloatField("Peso Mínimo", validators=[DataRequired()])
    imc = FloatField("IMC", validators=[DataRequired()])
    nutri_class = StringField("Classificação Nutricional", validators=[DataRequired()])
    necessidade_calorica = StringField("Necessidade Calórica", validators=[Optional()])
    ingestao_liquido = FloatField("Ingestão de Líquido", validators=[DataRequired()])
    idade_metabolica = IntegerField("Idade Metabólica", validators=[DataRequired()])
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
    pa = StringField("Pressão Arterial", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class SkinfoldMeasurementForm(FlaskForm):
    data_medicao = DateField("Data de Medição", format="%Y-%m-%d", validators=[DataRequired()])
    massa_muscular = FloatField("Massa Muscular", validators=[DataRequired()])
    gordura = FloatField("Gordura", validators=[DataRequired()])
    abdominal = FloatField("Abdominal", validators=[DataRequired()])
    cintura = FloatField("Cintura", validators=[DataRequired()])
    quadril = FloatField("Quadril", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class DietForm(FlaskForm):
    name = SelectField("Nome da Dieta", validators=[DataRequired()])
    other_name = StringField("Outro (especifique)", validators=[Optional()])
    description = TextAreaField("Descrição", validators=[Optional()])
    pdf_file = FileField("Arquivo PDF", validators=[Optional()])
    submit = SubmitField("Salvar")

    def __init__(self, *args, **kwargs):
        super(DietForm, self).__init__(*args, **kwargs)
        # Static Options
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
        # Search for Diets added that stil are not present in the static choices
        extra_choices = [
            (diet.name, diet.name)
            for diet in Diet.query.all()
            if diet.name.lower() not in [choice[0].lower() for choice in fixed_choices]
        ]
        self.name.choices = fixed_choices + extra_choices + [("Outro", "Outro")]
