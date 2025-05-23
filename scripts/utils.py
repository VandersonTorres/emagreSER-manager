import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
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
        from_=f"whatsapp:{app.config['TWILIO_PHONE']}",
        to=f"whatsapp:{telephone}",
        media_url=[diet_file_url],
    )
    return message.sid


def hex_to_rgb_normalized(color_str, app):
    try:
        # Case 1: rgb(255, 0, 0)
        if color_str.startswith("rgb"):
            rgb = re.findall(r"\d+", color_str)
            if len(rgb) == 3:
                r, g, b = [int(c) / 255.0 for c in rgb]
                return r, g, b

        # Case 2: #FF0000
        color_str = color_str.lstrip("#")
        if len(color_str) == 6:
            r = int(color_str[0:2], 16) / 255.0
            g = int(color_str[2:4], 16) / 255.0
            b = int(color_str[4:6], 16) / 255.0
            return r, g, b
    except Exception as e:
        app.logger.warning(f"Erro ao converter cor: {color_str}, {e}")

    return 0, 0, 0  # fallback


def extract_public_id_from_cloudinary(url: str) -> str:
    """
    Remove the domain and the extension of an Cloudinary URL.
    Exemple: https://.../diets/temp/file.pdf -> diets/temp/file
    """
    path = urlparse(url).path  # /raw/upload/vXXX/diets/temp/file.pdf
    parts = path.split("/")
    if "upload" in parts:
        idx = parts.index("upload")
        relevant = parts[idx + 1 :]  # ["v12345678", "diets", "temp", "arquivo.pdf"]
        filename = "/".join(relevant[1:])  # skip "v12345678"
        return os.path.splitext(filename)[0]  # remove .pdf
    return ""
