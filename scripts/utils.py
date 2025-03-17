from datetime import timedelta

from flask import flash, redirect, url_for

from app.models import Schedules


def block_access_to_patients(patient, user, msg, to_redirect):
    """Function to restrict a improper access in Patients Routes"""
    if "nutritionist" in [role.name for role in user.roles]:
        if patient.specialist.email != user.email:
            flash(msg, "danger")
            return redirect(url_for(to_redirect))


def is_valid_time(candidate, specialist):
    """Function that checks if a schedule is available"""
    lower_bound = candidate - timedelta(minutes=30)
    upper_bound = candidate + timedelta(minutes=30)

    conflict = Schedules.query.filter(
        Schedules.specialist == specialist, Schedules.date_time >= lower_bound, Schedules.date_time <= upper_bound
    ).first()
    return conflict is None
