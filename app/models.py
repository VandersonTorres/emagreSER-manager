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
    name = db.Column(db.String(255), unique=True, nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)  # 000.000.000-00
    tel_number = db.Column(db.String(14), unique=True, nullable=False)  # (31)90000-0000
    started_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # user = db.relationship("User", backref="pacients", lazy=True)

    def __repr__(self):
        return f"<Pacient {self.name} | {self.cpf}>"


# Pacients Historic model
class Historic(db.Model):
    __tablename__ = "historic"

    id = db.Column(db.Integer, primary_key=True)
    pacient_id = db.Column(db.Integer, db.ForeignKey("pacients.id"), nullable=False)
    pacient_name = db.Column(db.String, db.ForeignKey("pacients.name"), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    imc = db.Column(db.Float)
    date = db.Column(db.DateTime, db.ForeignKey("pacients.started_at"), nullable=False)

    # pacient = db.relationship("Pacients", backref="historic")

    def __repr__(self):
        return f"<Historic {self.pacient_name} - {self.date}>"


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
    pacient_id = db.Column(db.Integer, db.ForeignKey("pacients.id"), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String, default="pendente")

    # pacient = db.relationship("Pacients", backref="schedules")
