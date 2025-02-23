from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
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


class AnthropometricAssessmentForm(FlaskForm):
    data_avaliacao = DateField("Data de Avaliação", format="%Y-%m-%d", validators=[DataRequired()])
    ultima_guia = StringField("Nome da Última Guia", validators=[DataRequired()])
    idade = IntegerField("Idade", validators=[DataRequired()])
    altura = FloatField("Altura (m)", validators=[DataRequired()])
    peso = FloatField("Peso (kg)", validators=[DataRequired()])
    evolucao = StringField("Evolução", validators=[Optional()])
    p_max = FloatField("Peso Máximo", validators=[DataRequired()])
    p_ide = FloatField("Peso Ideal", validators=[DataRequired()])
    p_min = FloatField("Peso Mínimo", validators=[DataRequired()])
    imc = FloatField("IMC", validators=[DataRequired()])
    nutri_class = SelectField(
        "Classificação Nutricional",
        choices=[
            ("", "Selecione"),
            ("Abaixo", "Abaixo do Peso"),
            ("Normal", "Peso Normal"),
            ("Sobrepeso", "Sobrepeso"),
            ("Grau I", "Obesidade Grau I"),
            ("Grau II", "Obesidade Grau II"),
            ("Grau III", "Obesidade Grau III"),
        ],
        validators=[DataRequired()],
    )
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
    pa = FloatField("Pressão Arterial", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class SkinfoldMeasurementForm(FlaskForm):
    data_medicao = DateField("Data de Medição", format="%Y-%m-%d", validators=[DataRequired()])
    triciptal = FloatField("Tricipital", validators=[DataRequired()])
    bicipital = FloatField("Bicipital", validators=[DataRequired()])
    subscapula = FloatField("Subscápula", validators=[DataRequired()])
    toracica = FloatField("Torácica", validators=[Optional()])
    axilar = FloatField("Axilar Média", validators=[DataRequired()])
    supra = FloatField("Supra Ilíaca", validators=[DataRequired()])
    abdominal = FloatField("Abdominal", validators=[DataRequired()])
    coxa = FloatField("Coxa", validators=[DataRequired()])
    panturrilha = FloatField("Panturrilha", validators=[DataRequired()])

    submit = SubmitField("Salvar")


class DietForm(FlaskForm):
    name = SelectField(
        "Nome da Dieta",
        choices=[
            ("cetogenica", "Dieta Cetogênica"),
            ("low_carb_i", "Dieta Low Carb I"),
            ("low_carb_ii", "Dieta Low Carb II"),
            ("low_carb_iii", "Dieta Low Carb III"),
            ("termogenico_n3", "Dieta Termogênico N3"),
            ("guia_n2", "Dieta Guia N2"),
            ("guia_n5", "Dieta Guia N5"),
            ("detox", "Dieta Detox"),
            ("violeta", "Dieta Violeta"),
            ("laxativa", "Dieta Laxativa"),
            ("primavera", "Dieta Primavera"),
            ("zero_acucar", "Dieta Zero Açucar"),
            ("outro", "Outro"),
        ],
        validators=[DataRequired()],
    )
    other_name = StringField("Outro (especifique)", validators=[Optional()])
    description = TextAreaField("Descrição", validators=[Optional()])
    pdf_file = FileField("Arquivo PDF", validators=[FileAllowed(["pdf"], "Apenas arquivos PDF são permitidos.")])
    submit = SubmitField("Salvar")
