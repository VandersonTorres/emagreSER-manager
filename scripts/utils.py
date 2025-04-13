from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import flash, redirect, url_for
from sqlalchemy import func
from twilio.rest import Client

from app.models import Schedules


def block_access_to_patients(patient, user, msg, to_redirect):
    """Function to restrict a improper access in Patients Routes"""
    if "nutritionist" in [role.name for role in user.roles]:
        # If the nutri is original responsible for the patient
        if patient.specialist.email == user.email:
            return False  # Allow Access

        # Verify if the patient has an appointment with the specialist
        now = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        has_future_schedule = Schedules.query.filter(
            Schedules.patient_id == patient.id,
            Schedules.specialist == user.username,
            func.date(Schedules.date_time) >= now,
        ).first()

        if has_future_schedule:
            return False  # Allow Access

        # Block the access
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


def twilio_send_diet(patient, telephone, diet, diet_file_url, app):
    client = Client(app.config["TWILIO_SID"], app.config["TWILIO_AUTH"])
    message_text = f"Olá {patient}, aqui está sua dieta dessa semana:\n{diet}"
    message = client.messages.create(
        body=message_text,
        from_=f'whatsapp:{app.config["TWILIO_PHONE"]}',
        to=f"whatsapp:{telephone}",
        media_url=[diet_file_url],
    )
    return message.sid


def hex_to_rgb_normalized(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return 0, 0, 0  # fallback
    r, g, b = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return r, g, b
