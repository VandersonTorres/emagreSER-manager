from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_security import roles_required
from app.models import Schedules, Pacients, db

schedules_bp = Blueprint("schedules", __name__)


@schedules_bp.route("/schedules", methods=["GET"])
@roles_required("admin")
def list_schedules():
    schedules = Schedules.query.all()
    return render_template("admin/list_schedules.html", schedules=schedules)


@schedules_bp.route("/schedule_action", methods=["GET", "POST"])
@roles_required("admin")
def schedule_action():
    if request.method == "POST":
        pacient_id = request.form["pacient_id"]
        date_time = request.form["date_time"]

        schedule = Schedules(pacient_id=pacient_id, date_time=date_time)
        db.session.add(schedule)
        db.session.commit()

        flash("Consulta agendada com sucesso!")
        return redirect(url_for("schedules.list_schedules"))

    pacients = Pacients.query.all()
    return render_template("admin/schedule_action.html", pacients=pacients)


@schedules_bp.route("/schedules/delete/<int:id>", methods=["POST"])
@roles_required("admin")
def delete_schedule(id):
    schedule = Schedules.query.get_or_404(id)
    db.session.delete(schedule)
    db.session.commit()

    flash("Agendamento removido com sucesso!")
    return redirect(url_for("schedules.list_schedules"))
