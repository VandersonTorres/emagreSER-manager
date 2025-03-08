from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_security import roles_required

from app.models import Patients, Schedules, Specialists, db

schedules_bp = Blueprint("schedules", __name__)


def is_valid_time(candidate, specialist):
    """Function that checks if a schedule is available"""
    lower_bound = candidate - timedelta(minutes=30)
    upper_bound = candidate + timedelta(minutes=30)

    conflict = Schedules.query.filter(
        Schedules.specialist == specialist, Schedules.date_time >= lower_bound, Schedules.date_time <= upper_bound
    ).first()
    return conflict is None


@schedules_bp.route("/schedules", methods=["GET"])
@roles_required("admin")
def list_schedules():
    now = datetime.now()

    # Update status of expired schedules
    expired_schedules = Schedules.query.filter(Schedules.date_time < now, Schedules.status == "pendente").all()
    for schedule in expired_schedules:
        schedule.status = "finalizado"

    if expired_schedules:
        db.session.commit()

    specialists = Specialists.query.all()
    schedules_by_specialist = {}
    for specialist in specialists:
        schedules_by_specialist[specialist.name] = (
            Schedules.query.filter_by(specialist=specialist.name).order_by(Schedules.date_time).all()
        )

    return render_template("admin/schedules/list_schedules.html", schedules_by_specialist=schedules_by_specialist)


@schedules_bp.route("/schedule_action", methods=["GET", "POST"])
@roles_required("admin")
def schedule_action():
    specialists = Specialists.query.all()
    if request.method == "POST":
        patient_name = request.form["patient_name"]
        date_time_str = request.form["date_time"]
        specialist = request.form["specialist"]
        date_time = datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M")

        lower_bound = date_time - timedelta(minutes=30)
        upper_bound = date_time + timedelta(minutes=30)
        conflict = Schedules.query.filter(
            Schedules.specialist == specialist, Schedules.date_time >= lower_bound, Schedules.date_time <= upper_bound
        ).first()

        if conflict:
            suggestions = []

            # Search for nearby appointments time after the requested (about 2 hours)
            candidate = date_time + timedelta(minutes=0)
            end_candidate = date_time + timedelta(hours=2)
            while candidate <= end_candidate and len(suggestions) < 3:
                if is_valid_time(candidate, specialist):
                    suggestions.append(candidate.strftime("%d/%m/%Y %H:%M"))
                candidate += timedelta(minutes=10)

            # Search for nearby appointments time before the requested (about 2 hours)
            before_suggestions = []
            candidate = date_time - timedelta(minutes=0)
            start_candidate = date_time - timedelta(hours=2)
            while candidate >= start_candidate and len(before_suggestions) < 3:
                if is_valid_time(candidate, specialist):
                    before_suggestions.append(candidate.strftime("%d/%m/%Y %H:%M"))
                candidate -= timedelta(minutes=10)
            before_suggestions.reverse()  # Closest first

            # Combine the both, before and after
            all_suggestions = before_suggestions + suggestions
            suggestions_str = ", ".join(all_suggestions) if all_suggestions else "Nenhum horário disponível próximo"

            flash(
                f"Erro: já existe um agendamento para este profissional em um horário próximo. \n"
                f"Horários sugeridos: {suggestions_str}"
            )
            return redirect(url_for("schedules.schedule_action"))

        schedule = Schedules(patient_name=patient_name, date_time=date_time, specialist=specialist)
        db.session.add(schedule)
        db.session.commit()

        flash("Consulta agendada com sucesso!")
        return redirect(url_for("schedules.list_schedules"))

    patients = Patients.query.all()
    return render_template("admin/schedules/schedule_action.html", patients=patients, specialists=specialists)


@schedules_bp.route("/schedules/delete/<int:id>", methods=["POST"])
@roles_required("admin")
def delete_schedule(id):
    schedule = Schedules.query.get_or_404(id)
    db.session.delete(schedule)
    db.session.commit()

    flash("Agendamento removido com sucesso!")
    return redirect(url_for("schedules.list_schedules"))
