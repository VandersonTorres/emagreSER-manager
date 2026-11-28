"""Database models of the clinic: users and roles, specialists, patients with their records, diets and schedules."""

from flask_security.models import fsqla_v3 as fsqla
from flask_sqlalchemy import SQLAlchemy

from app.dates import clinic_today, utc_now

db = SQLAlchemy()

fsqla.FsModels.set_db_info(db)


class Role(db.Model, fsqla.FsRoleMixin):
    """Role that grants access to part of the system; the columns come from Flask-Security."""


class User(db.Model, fsqla.FsUserMixin):
    """Account that signs in to the system; the columns come from Flask-Security."""


class Specialists(db.Model):
    """Professional who looks after patients."""

    __tablename__ = "specialists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    tel_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self) -> str:
        """Describe the specialist by name and CPF.

        :return: The text shown in logs and in the shell.
        """
        return f"<Specialist {self.name} | {self.cpf}>"


class Patients(db.Model):
    """Patient with the personal data, the clinical history and the behavioral history.

    The CPF and the e-mail are optional, so they cannot be unique. ``started_at`` is the UTC time of the registration,
    stored without time zone and filled when the row is inserted. ``hours`` is the time of the physical activities.
    ``heartburn`` is no longer asked: new patients get an empty answer and the answers already stored are kept.
    """

    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    cpf = db.Column(db.String(14), nullable=True)
    tel_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    started_at = db.Column(db.DateTime, default=utc_now)
    specialist_id = db.Column(db.Integer, db.ForeignKey("specialists.id"), nullable=True)

    medication = db.Column(db.String(3), nullable=False)
    medications_details = db.Column(db.Text, nullable=True)
    intestine = db.Column(db.Integer, nullable=False)
    allergies = db.Column(db.String(3), nullable=False)
    allergies_details = db.Column(db.Text, nullable=True)
    water = db.Column(db.Float, nullable=False)
    heartburn = db.Column(db.String(3), nullable=False)

    physical_activities = db.Column(db.String(3), nullable=False)
    physical_details = db.Column(db.Text, nullable=True)
    hours = db.Column(db.Time, nullable=True)
    frequency = db.Column(db.Integer, nullable=False, default=0)
    objective = db.Column(db.Text, nullable=False)

    anthropometric_evaluations = db.relationship(
        "AnthropometricEvaluation", backref="patient", cascade="all, delete-orphan", passive_deletes=True
    )
    skinfolds = db.relationship("SkinFolds", backref="patient", cascade="all, delete-orphan", passive_deletes=True)
    specialist = db.relationship("Specialists", backref="patients")

    def __repr__(self) -> str:
        """Describe the patient by name and CPF.

        :return: The text shown in logs and in the shell.
        """
        return f"<Patient {self.name} | {self.cpf}>"


class AnthropometricEvaluation(db.Model):
    """Anthropometric evaluation of a patient; the date defaults to today in the São Paulo time zone."""

    __tablename__ = "anthropometric_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    data_avaliacao = db.Column(db.Date, nullable=False, default=clinic_today)
    ultima_guia = db.Column(db.String(255), nullable=False, default="Nenhuma")
    idade = db.Column(db.Integer, nullable=False)
    evolucao = db.Column(db.Text, nullable=True)
    p_max = db.Column(db.Float, nullable=False)
    p_ide = db.Column(db.Float, nullable=False)
    p_min = db.Column(db.Float, nullable=False)
    imc = db.Column(db.Float, nullable=False)
    nutri_class = db.Column(db.String(20), nullable=False)
    necessidade_calorica = db.Column(db.String(100), nullable=True)
    ingestao_liquido = db.Column(db.Float, nullable=False)
    grau_atv_fisica = db.Column(db.String(20), nullable=False)
    specialist_name = db.Column(db.String(100), nullable=True)

    def __repr__(self) -> str:
        """Describe the evaluation by patient id and date.

        :return: The text shown in logs and in the shell.
        """
        return f"<AnthropometricEvaluation {self.patient_id} | {self.data_avaliacao}>"


class SkinFolds(db.Model):
    """Bioimpedance measurement of a patient; the date defaults to today in the São Paulo time zone.

    ``observacoes`` is an optional note of the nutritionist; the record shows the one of the latest measurement.
    """

    __tablename__ = "skinfolds"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    data_medicao = db.Column(db.Date, nullable=False, default=clinic_today)
    altura = db.Column(db.Float, nullable=False)
    peso = db.Column(db.Float, nullable=False)
    massa_muscular = db.Column(db.Float, default=0, nullable=False)
    gordura = db.Column(db.Float, default=0, nullable=False)
    abdominal = db.Column(db.Float, default=0, nullable=False)
    cintura = db.Column(db.Float, default=0, nullable=False)
    quadril = db.Column(db.Float, default=0, nullable=False)
    idade_metabolica = db.Column(db.Integer, default=0, nullable=False)
    pa = db.Column(db.String(6), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        """Describe the measurement by patient id and date.

        :return: The text shown in logs and in the shell.
        """
        return f"<SkinFolds {self.patient_id} | {self.data_medicao}>"


class Diet(db.Model):
    """Diet guide with its original PDF and, when edited, the temporary edited file."""

    __tablename__ = "diets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    diet_file = db.Column(db.String(255), nullable=True)
    temp_diet_file = db.Column(db.String(255), nullable=True)
    order = db.Column(db.Integer, default=0)

    def __repr__(self) -> str:
        """Describe the diet by name.

        :return: The text shown in logs and in the shell.
        """
        return f"<Diet {self.name}>"


class Schedules(db.Model):
    """Appointment of a patient with a specialist."""

    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    specialist = db.Column(db.String, nullable=False)
    status = db.Column(db.String, default="pendente")

    patient = db.relationship("Patients", backref="schedules")

    def __repr__(self) -> str:
        """Describe the appointment by patient id, specialist and time.

        :return: The text shown in logs and in the shell.
        """
        return f"<Schedule {self.patient_id} | {self.specialist} | {self.date_time}>"
