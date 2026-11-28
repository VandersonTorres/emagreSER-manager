"""Agenda of the professionals: list the schedules, book a visit avoiding conflicts and cancel a visit."""

from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_security import current_user, roles_accepted
from sqlalchemy import func

from app.dates import clinic_today
from app.models import Patients, Schedules, Specialists, db
from scripts.utils import is_valid_time

schedules_bp = Blueprint("schedules", __name__)


@schedules_bp.route("/schedules", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def list_schedules() -> ResponseReturnValue:
    """Render the schedules of each professional, optionally of the day given in the "date" argument.

    Pending schedules of past days become finished first. Without a date, finished schedules of more than one day ago
    are left out. A "date" that is not a valid ``YYYY-MM-DD`` day is flashed as an error and ignored. A nutritionist
    only sees their own schedules; admin and secretary see the ones of every professional.

    :return: The rendered agenda page, or a redirect to the home page when the nutritionist has no professional record.
    """
    now = clinic_today()

    expired_schedules = Schedules.query.filter(
        func.date(Schedules.date_time) < now, Schedules.status == "pendente"
    ).all()
    for schedule in expired_schedules:
        schedule.status = "finalizado"

    if expired_schedules:
        db.session.commit()

    date_str = request.args.get("date")
    date_filter = None
    if date_str:
        try:
            date_filter = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Data inválida.", "danger")

    def filter_schedules(specialist_name: str) -> list[Schedules]:
        """List the schedules of a professional, in time order, for the chosen day or for the default period.

        :param specialist_name: Name of the professional.
        :return: The schedules of the professional.
        """
        query = Schedules.query.filter_by(specialist=specialist_name)
        if not date_filter:
            return (
                query.filter(
                    ~((Schedules.status == "finalizado") & (func.date(Schedules.date_time) < now - timedelta(days=1)))
                )
                .order_by(Schedules.date_time)
                .all()
            )
        return query.filter(func.date(Schedules.date_time) == date_filter).order_by(Schedules.date_time).all()

    page_context = {"date_filter": date_filter, "today": now, "tomorrow": now + timedelta(days=1)}

    if "nutritionist" in [role.name for role in current_user.roles]:
        specialist = Specialists.query.filter_by(email=current_user.email).first()
        if not specialist:
            flash("Erro: Especialista não encontrado.")
            return redirect(url_for("main.index"))

        schedules = filter_schedules(specialist.name)
        return render_template(
            "admin/schedules/list_schedules.html", schedules_by_specialist={specialist.name: schedules}, **page_context
        )

    schedules_by_specialist = {
        specialist.name: filter_schedules(specialist.name) for specialist in Specialists.query.all()
    }

    return render_template(
        "admin/schedules/list_schedules.html", schedules_by_specialist=schedules_by_specialist, **page_context
    )


def parse_visit_time(text: str) -> datetime | None:
    """Read the date and time of the booking form.

    :param text: Value of the ``datetime-local`` field, as ``YYYY-MM-DDTHH:MM``.
    :return: The time as typed, without time zone conversion, or ``None`` when the text is not a valid time.
    """
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def find_patient(patient_id: str) -> Patients | None:
    """Look up the patient of the booking form.

    :param patient_id: Value of the patient field.
    :return: The patient, or ``None`` when the value is not the id of a patient.
    """
    if not patient_id.isdecimal():
        return None
    return db.session.get(Patients, int(patient_id))


@schedules_bp.route("/schedule_action", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def schedule_action() -> ResponseReturnValue:
    """Show the booking form and, on POST, book the visit unless the professional has a visit around that time.

    A missing or unknown patient, a missing professional and an invalid date flash an error and send the user back to
    the form without storing anything. On a conflict the closest free times, before and after, are suggested.

    :return: The form page, or a redirect to the form after an error, or to the agenda after booking.
    """
    patients = Patients.query.all()
    specialists = Specialists.query.all()

    if "nutritionist" in [role.name for role in current_user.roles]:
        patients = Patients.query.join(Specialists).filter(Specialists.email == current_user.email).all()
        if specialist := Specialists.query.filter_by(email=current_user.email).first():
            specialist = specialist.name
        else:
            flash("Erro: Especialista não encontrado.")
            return redirect(url_for("main.index"))

    if request.method == "POST":
        patient_id = request.form.get("patient_id", "").strip()
        date_time_str = request.form.get("date_time", "").strip()
        specialist = request.form.get("specialist", "")

        if not patient_id:
            flash("Erro: selecione o paciente da consulta.", "danger")
            return redirect(url_for("schedules.schedule_action"))
        patient = find_patient(patient_id)
        if patient is None:
            flash("Erro: paciente não encontrado. Selecione um paciente da lista.", "danger")
            return redirect(url_for("schedules.schedule_action"))
        if not specialist.strip():
            flash("Erro: selecione o profissional da consulta.", "danger")
            return redirect(url_for("schedules.schedule_action"))
        date_time = parse_visit_time(date_time_str)
        if date_time is None:
            flash("Erro: informe uma data e hora válidas para a consulta.", "danger")
            return redirect(url_for("schedules.schedule_action"))

        lower_bound = date_time - timedelta(minutes=14)
        upper_bound = date_time + timedelta(minutes=14)
        conflict = Schedules.query.filter(
            Schedules.specialist == specialist, Schedules.date_time >= lower_bound, Schedules.date_time <= upper_bound
        ).first()

        if conflict:
            suggestions = []

            candidate = date_time + timedelta(minutes=0)
            end_candidate = date_time + timedelta(hours=2)
            while candidate <= end_candidate and len(suggestions) < 3:
                if is_valid_time(candidate, specialist):
                    suggestions.append(candidate.strftime("%d/%m/%Y %H:%M"))
                candidate += timedelta(minutes=10)

            before_suggestions = []
            candidate = date_time - timedelta(minutes=0)
            start_candidate = date_time - timedelta(hours=2)
            while candidate >= start_candidate and len(before_suggestions) < 3:
                if is_valid_time(candidate, specialist):
                    before_suggestions.append(candidate.strftime("%d/%m/%Y %H:%M"))
                candidate -= timedelta(minutes=10)
            before_suggestions.reverse()

            all_suggestions = before_suggestions + suggestions
            suggestions_str = ", ".join(all_suggestions) if all_suggestions else "Nenhum horário disponível próximo"

            flash(
                f"Erro: já existe um agendamento para este profissional em um horário próximo. \n"
                f"Horários sugeridos: {suggestions_str}"
            )
            return redirect(url_for("schedules.schedule_action"))

        schedule = Schedules(patient_id=patient.id, date_time=date_time, specialist=specialist)
        db.session.add(schedule)
        db.session.commit()

        flash(f"Consulta para '{schedule.patient.name}' agendada com o profissional '{specialist}' com sucesso!")
        return redirect(url_for("schedules.list_schedules"))

    return render_template("admin/schedules/schedule_action.html", patients=patients, specialists=specialists)


@schedules_bp.route("/schedules/delete/<int:id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_schedule(id: int) -> ResponseReturnValue:
    """Delete a schedule; a nutritionist without a professional record is sent back to the home page.

    :param id: Id of the schedule.
    :raises NotFound: If the schedule does not exist.
    :return: A redirect to the agenda, or to the home page.
    """
    if "nutritionist" in [role.name for role in current_user.roles]:
        specialist = Specialists.query.filter_by(email=current_user.email).first()
        if not specialist:
            flash("Erro: Especialista não encontrado.")
            return redirect(url_for("main.index"))

    schedule = Schedules.query.get_or_404(id)
    db.session.delete(schedule)
    db.session.commit()

    flash("Agendamento removido com sucesso!")
    return redirect(url_for("schedules.list_schedules"))
