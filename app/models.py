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
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    tel_number = db.Column(db.String(14), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # user = db.relationship("User", backref="pacients", lazy=True)

    def __repr__(self):
        return f"<Pacient {self.name} | {self.cpf}>"


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
