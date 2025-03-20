from datetime import timedelta

from flask import flash, redirect, url_for
from twilio.rest import Client

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


def twilio_send_diet(patient, telephone, diet, pdf_url, app):
    client = Client(app.config["TWILIO_SID"], app.config["TWILIO_AUTH"])
    message_text = f"Olá {patient}, aqui está sua dieta dessa semana:\n{diet}"
    message = client.messages.create(
        body=message_text, from_=app.config["TWILIO_PHONE"], to=telephone, media_url=[pdf_url]
    )
    return message.sid
