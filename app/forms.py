from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed


class PacientForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired()])
    cpf = StringField("CPF", validators=[DataRequired()])
    tel_number = StringField("Telefone", validators=[DataRequired()])
    submit = SubmitField("Salvar")


class HistoricForm(FlaskForm):
    weight = StringField("Peso (kg)", validators=[DataRequired()])
    height = StringField("Altura (cm)", validators=[DataRequired()])
    imc = StringField("IMC", validators=[DataRequired()])
    submit = SubmitField("Salvar")


class DietForm(FlaskForm):
    name = StringField("Nome da Dieta", validators=[DataRequired()])
    description = TextAreaField("Descrição", validators=[DataRequired()])
    pdf_file = FileField("Arquivo PDF", validators=[FileAllowed(['pdf'], "Apenas arquivos PDF são permitidos.")])
    submit = SubmitField("Salvar")
