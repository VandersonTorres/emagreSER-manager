from datetime import datetime, timezone

from flask_security.models import fsqla_v3 as fsqla
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

fsqla.FsModels.set_db_info(db)


class Role(db.Model, fsqla.FsRoleMixin):
    pass


class User(db.Model, fsqla.FsUserMixin):
    pass


class Specialists(db.Model):
    __tablename__ = "specialists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    tel_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<Specialist {self.name} | {self.cpf}>"


class Patients(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)

    # Dados pessoais
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    cpf = db.Column(db.String(14), nullable=True)  # Can not be unique because it is still Optional
    tel_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=True)  # Can not be unique because it is still Optional
    started_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    specialist_id = db.Column(db.Integer, db.ForeignKey("specialists.id"), nullable=True)

    # História Clínica
    medication = db.Column(db.String(3), nullable=False)
    medications_details = db.Column(db.Text, nullable=True)
    intestine = db.Column(db.Integer, nullable=False)
    allergies = db.Column(db.String(3), nullable=False)
    allergies_details = db.Column(db.Text, nullable=True)
    water = db.Column(db.Float, nullable=False)
    heartburn = db.Column(db.String(3), nullable=False)

    # História Comportamental
    physical_activities = db.Column(db.String(3), nullable=False)
    physical_details = db.Column(db.Text, nullable=True)
    hours = db.Column(db.Time, nullable=True)  # Physical activities hours
    frequency = db.Column(db.Integer, nullable=False, default=0)
    objective = db.Column(db.Text, nullable=False)

    anthropometric_evaluations = db.relationship(
        "AnthropometricEvaluation", backref="patient", cascade="all, delete-orphan", passive_deletes=True
    )
    skinfolds = db.relationship("SkinFolds", backref="patient", cascade="all, delete-orphan", passive_deletes=True)
    specialist = db.relationship("Specialists", backref="patients")

    def __repr__(self):
        return f"<Patient {self.name} | {self.cpf}>"


class AnthropometricEvaluation(db.Model):
    __tablename__ = "anthropometric_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    data_avaliacao = db.Column(db.Date, nullable=False, default=datetime.now(timezone.utc))
    ultima_guia = db.Column(db.String(20), nullable=False, default="Nenhuma")
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

    def __repr__(self):
        return f"<AnthropometricEvaluation {self.patient_id} | {self.data_avaliacao}>"


class SkinFolds(db.Model):
    __tablename__ = "skinfolds"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    data_medicao = db.Column(db.Date, nullable=False, default=datetime.now(timezone.utc))
    altura = db.Column(db.Float, nullable=False)
    peso = db.Column(db.Float, nullable=False)
    massa_muscular = db.Column(db.Float, default=0, nullable=False)
    gordura = db.Column(db.Float, default=0, nullable=False)
    abdominal = db.Column(db.Float, default=0, nullable=False)
    cintura = db.Column(db.Float, default=0, nullable=False)
    quadril = db.Column(db.Float, default=0, nullable=False)
    idade_metabolica = db.Column(db.Integer, default=0, nullable=False)
    pa = db.Column(db.String(6), nullable=False)

    def __repr__(self):
        return f"<SkinFolds {self.patient_id} | {self.data_medicao}>"


class Diet(db.Model):
    __tablename__ = "diets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    pdf_file = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Diet {self.name}>"


class Schedules(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    specialist = db.Column(db.String, nullable=False)
    status = db.Column(db.String, default="pendente")

    patient = db.relationship("Patients", backref="schedules")

    def __repr__(self):
        return f"<Schedule {self.patient_id} | {self.specialist} | {self.date_time}>"
