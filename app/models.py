from datetime import datetime, timezone

from flask_security.models import fsqla_v3 as fsqla
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Define models
fsqla.FsModels.set_db_info(db)


# Flask-Security Models
class Role(db.Model, fsqla.FsRoleMixin):
    pass


class User(db.Model, fsqla.FsUserMixin):
    pass


# Pacients model
class Pacients(db.Model):
    __tablename__ = "pacients"

    id = db.Column(db.Integer, primary_key=True)

    # Dados pessoais
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    tel_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

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
        "AnthropometricEvaluation", backref="pacient", cascade="all, delete-orphan", passive_deletes=True
    )
    skinfolds = db.relationship("SkinFolds", backref="pacient", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<Pacient {self.name} | {self.cpf}>"


# Anthropometric model
class AnthropometricEvaluation(db.Model):
    __tablename__ = "anthropometric_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    pacient_id = db.Column(db.Integer, db.ForeignKey("pacients.id", ondelete="CASCADE"), nullable=False)
    data_avaliacao = db.Column(db.Date, nullable=False, default=datetime.now(timezone.utc))
    ultima_guia = db.Column(db.String(20), nullable=False)
    idade = db.Column(db.Integer, nullable=False)
    altura = db.Column(db.Float, nullable=False)
    peso = db.Column(db.Float, nullable=False)
    evolucao = db.Column(db.Text, nullable=True)
    p_max = db.Column(db.Float, nullable=False)
    p_ide = db.Column(db.Float, nullable=False)
    p_min = db.Column(db.Float, nullable=False)
    imc = db.Column(db.Float, nullable=False)
    nutri_class = db.Column(db.String(20), nullable=False)
    grau_atv_fisica = db.Column(db.String(20), nullable=False)
    pa = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<AnthropometricEvaluation {self.pacient_id} | {self.date}>"


# SkinFolds model
class SkinFolds(db.Model):
    __tablename__ = "skinfolds"

    id = db.Column(db.Integer, primary_key=True)
    pacient_id = db.Column(db.Integer, db.ForeignKey("pacients.id", ondelete="CASCADE"), nullable=False)
    data_medicao = db.Column(db.Date, nullable=False, default=datetime.now(timezone.utc))
    triciptal = db.Column(db.Float, nullable=False)
    bicipital = db.Column(db.Float, nullable=False)
    subscapula = db.Column(db.Float, nullable=False)
    toracica = db.Column(db.Float, nullable=True)
    axilar = db.Column(db.Float, nullable=False)
    supra = db.Column(db.Float, nullable=False)
    abdominal = db.Column(db.Float, nullable=False)
    coxa = db.Column(db.Float, nullable=False)
    panturrilha = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<SkinFolds {self.pacient_id} | {self.date}>"


# Diet model
class Diet(db.Model):
    __tablename__ = "diets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    pdf_file = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Diet {self.name}>"


# Schedules model
class Schedules(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    pacient_name = db.Column(db.String(255), db.ForeignKey("pacients.name"), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    specialist = db.Column(db.String, nullable=False)
    status = db.Column(db.String, default="pendente")

    pacient = db.relationship("Pacients", backref="schedules")

    def __repr__(self):
        return f"<Schedule {self.pacient_name} | {self.specialist} | {self.date_time}>"
