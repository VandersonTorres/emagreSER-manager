from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_security import roles_required

from app.models import Patients, Schedules, db

schedules_bp = Blueprint("schedules", __name__)


@schedules_bp.route("/schedules", methods=["GET"])
@roles_required("admin")
def list_schedules():
    schedules = Schedules.query.all()
    return render_template("admin/schedules/list_schedules.html", schedules=schedules)


@schedules_bp.route("/schedule_action", methods=["GET", "POST"])
@roles_required("admin")
def schedule_action():
    if request.method == "POST":
        patient_name = request.form["patient_name"]
        date_time_str = request.form["date_time"]
        specialist = request.form["specialist"]
        date_time = datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M")

        schedule = Schedules(patient_name=patient_name, date_time=date_time, specialist=specialist)
        db.session.add(schedule)
        db.session.commit()

        flash("Consulta agendada com sucesso!")
        return redirect(url_for("schedules.list_schedules"))

    patients = Patients.query.all()
    return render_template("admin/schedules/schedule_action.html", patients=patients)


@schedules_bp.route("/schedules/delete/<int:id>", methods=["POST"])
@roles_required("admin")
def delete_schedule(id):
    schedule = Schedules.query.get_or_404(id)
    db.session.delete(schedule)
    db.session.commit()

    flash("Agendamento removido com sucesso!")
    return redirect(url_for("schedules.list_schedules"))
