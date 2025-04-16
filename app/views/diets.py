import os
import re
from datetime import datetime
from smtplib import SMTPAuthenticationError, SMTPSenderRefused
from zoneinfo import ZoneInfo

import fitz
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_mail import Message
from flask_security import current_user, roles_accepted
from sqlalchemy import func
from twilio.base.exceptions import TwilioRestException
from werkzeug.utils import secure_filename

from app.extensions import mail
from app.forms import DietForm
from app.models import Diet, Patients, Schedules, Specialists, db
from scripts.utils import hex_to_rgb_normalized, twilio_send_diet

diets_bp = Blueprint("diets", __name__)


@diets_bp.route("/diets")
@roles_accepted("admin", "secretary", "nutritionist")
def list_diets():
    patients = Patients.query.all()
    if "nutritionist" in [role.name for role in current_user.roles]:
        now = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        patients = (
            Patients.query.join(Specialists, Patients.specialist_id == Specialists.id)
            .outerjoin(Schedules, Patients.id == Schedules.patient_id)
            .filter(
                (Specialists.email == current_user.email)
                | ((Schedules.specialist == current_user.username) & (func.date(Schedules.date_time) >= now))
            )
            .distinct()
            .all()
        )

    diets = Diet.query.all()
    return render_template("admin/diets/list_diets.html", patients=patients, diets=diets)


@diets_bp.route("/diets/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_diet():
    form = DietForm()
    if form.validate_on_submit():
        diet_filename = None
        if form.diet_file.data:
            diet_filename = secure_filename(form.diet_file.data.filename)
            diet_file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], diet_filename)
            form.diet_file.data.save(diet_file_path)

        diet_name = form.other_name.data if form.name.data == "Outro" else form.name.data
        diet = Diet(name=diet_name, description=form.description.data, diet_file=diet_filename)
        db.session.add(diet)
        db.session.commit()

        flash("Dieta cadastrada com sucesso!")
        return redirect(url_for("diets.list_diets"))

    return render_template("admin/diets/add_diet.html", form=form)


@diets_bp.route("/diets/<int:id>", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_diet(id):
    diet = Diet.query.get_or_404(id)
    pdf_url = url_for("diets.serve_file", filename=diet.diet_file, _external=True)
    return render_template("admin/diets/view_diet.html", diet=diet, pdf_url=pdf_url)


@diets_bp.route("/diets/delete/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_diet(id):
    diet = Diet.query.get_or_404(id)
    if request.method == "POST":
        # Remove the file
        if diet.diet_file:
            diet_file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], diet.diet_file)
            if os.path.exists(diet_file_path):
                os.remove(diet_file_path)

            temp_diet_file_path = os.path.join(current_app.config["TEMP_UPLOAD_FOLDER"], diet.temp_diet_file)
            if os.path.exists(temp_diet_file_path):
                os.remove(temp_diet_file_path)

        # Remove from database
        db.session.delete(diet)
        db.session.commit()
        flash(f"Dieta '{diet.name}' removida com sucesso!", "success")
        return redirect(url_for("diets.list_diets"))
    return render_template("admin/diets/delete_diet.html", diet=diet)


@diets_bp.route("/diets/download/<type_>/<filename>")
@roles_accepted("admin", "secretary", "nutritionist")
def download_diet(filename, type_="original"):
    if type_ == "temp":
        folder = current_app.config["TEMP_UPLOAD_FOLDER"]
    else:
        folder = current_app.config["UPLOAD_FOLDER"]

    return send_from_directory(folder, filename, as_attachment=True)


@diets_bp.route("/send_diet_email/<int:diet_id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def send_diet_email(diet_id):
    patient = Patients.query.get_or_404(request.form.get("patient_id"))
    patient_name = patient.name

    if not patient.email:
        flash(f"O paciente {patient_name} não possui email cadastrado.", "danger")
        return redirect(url_for("diets.list_diets"))

    diet = Diet.query.get_or_404(diet_id)
    temp_diet_file = diet.temp_diet_file
    if not temp_diet_file:
        flash(
            "Essa dieta não possui uma edição válida para o arquivo e não é possível enviar o arquivo original",
            "danger",
        )
        return redirect(url_for("diets.list_diets"))

    # Generating public URL for the File
    diet_file_url = url_for("diets.serve_file", filename=temp_diet_file, type_="temp", _external=True)

    msg = Message(
        subject=f"Dieta {diet.name}", recipients=[patient.email], sender=current_app.config.get("MAIL_DEFAULT_SENDER")
    )
    msg.charset = "utf-8"
    msg.body = (
        f"Olá, {patient_name},\n\n"
        f"Segue a sua dieta '{diet.name}' dessa semana.\n\n"
        f"Você pode acessar o arquivo através do link abaixo, ou encontrá-lo em anexo:\n"
        f"{diet_file_url}\n\n"
        "At.te, Equipe EmagreSER"
    )

    diet_file_path = os.path.join(current_app.config.get("TEMP_UPLOAD_FOLDER"), temp_diet_file)
    if not os.path.exists(diet_file_path):
        flash("Arquivo não encontrado no servidor.", "danger")
        return redirect(url_for("diets.list_diets"))
    try:
        with current_app.open_resource(diet_file_path, "rb") as fp:
            diet_file_data = fp.read()
            msg.attach(filename=temp_diet_file, content_type="application/pdf", data=diet_file_data)

        mail.send(msg)
        flash(f"Dieta '{diet.name}' enviada com sucesso para o e-mail do paciente '{patient_name}'!", "success")
    except (SMTPAuthenticationError, SMTPSenderRefused) as e:
        current_app.logger.error(f"Erro ao enviar e-mail: {e}")
        flash("Não foi possível enviar a dieta por e-mail. Consulte o suporte!", "danger")

    return redirect(url_for("diets.list_diets"))


@diets_bp.route("/send_diet/<int:diet_id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def send_diet_wpp(diet_id):
    patient = Patients.query.get_or_404(request.form.get("patient_id"))
    patient_name = patient.name
    cleaned_telephone = re.sub(r"[\s(),-]", "", patient.tel_number)
    if len(cleaned_telephone) == 11:
        telephone = f"+55{cleaned_telephone}"
    else:
        telephone = f"+55{cleaned_telephone[:2]}9{cleaned_telephone[2:len(cleaned_telephone)]}"

    diet = Diet.query.get_or_404(diet_id)
    temp_diet_file = diet.temp_diet_file
    if not temp_diet_file:
        flash(
            "Essa dieta não possui uma edição válida para o arquivo e não é possível enviar o arquivo original",
            "danger",
        )
        return redirect(url_for("diets.list_diets"))

    # Generating public URL for the File
    diet_file_url = url_for("diets.serve_file", filename=temp_diet_file, type_="temp", _external=True)
    try:
        # Send diet by WhatsApp
        response = twilio_send_diet(
            patient=patient_name,
            telephone=telephone,
            diet=diet.name,
            diet_file_url=diet_file_url,
            app=current_app,
        )
        flash(
            f"Dieta '{diet.name}' enviada com sucesso para o paciente '{patient_name}' - {telephone}! "
            f"ID de Confirmação: '{response}'",
            "success",
        )
        return redirect(url_for("diets.list_diets"))
    except TwilioRestException:
        flash("Não foi possível enviar a dieta com sucesso. Consulte o suporte!", "danger")
        return redirect(url_for("diets.list_diets"))


@diets_bp.route("/uploads/<type_>/<filename>")
def serve_file(filename, type_="original"):
    if type_ == "temp":
        return send_from_directory(current_app.config["TEMP_UPLOAD_FOLDER"], filename)
    else:
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@diets_bp.route("/diets/edit_diet/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_diet(id):
    diet = Diet.query.get_or_404(id)
    if not diet.diet_file:
        flash("Essa dieta não possui um arquivo.", "danger")
        return redirect(url_for("diets.list_diets"))

    if request.method == "POST":
        try:
            annotations = request.json.get("annotations")
            if not annotations:
                return jsonify({"status": "error", "message": "Não foi possível detectar alterações"}), 400

            pdf_path = os.path.join(current_app.config["UPLOAD_FOLDER"], diet.diet_file)
            doc = fitz.open(pdf_path)

            for ann in annotations:
                page_number = ann.get("page", 0) - 1
                if page_number < 0 or page_number >= len(doc):
                    current_app.logger.warning(f"Ignorando anotação com página inválida: {page_number}")
                    continue

                page = doc.load_page(page_number)
                text = ann.get("text", "")
                font_size = max(ann.get("fontSize", 11), 11)
                color = ann.get("color", "#000000")
                rgb = hex_to_rgb_normalized(color)

                # Get the canvas dimensions from the front
                x_canvas = ann.get("x", 0)
                y_canvas = ann.get("y", 0)
                canvas_width = ann.get("canvasWidth")
                canvas_height = ann.get("canvasHeight")

                if not canvas_width or not canvas_height:
                    current_app.logger.warning("Dimensões do canvas ausentes ou inválidas.")
                    continue

                # Real size of the page in point at the backend
                page_width = page.rect.width
                page_height = page.rect.height

                # coordinates convertion (proportional to real PDF)
                x_ratio = x_canvas / canvas_width
                y_ratio = y_canvas / canvas_height

                x_pdf = x_ratio * page_width
                y_pdf = y_ratio * page_height

                font = fitz.Font("helv")
                ascender = font.ascender
                descender = font.descender

                text_width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
                text_height = (ascender - descender) * font_size

                # Fix position
                x_pdf_adjusted = x_pdf - text_width / 2  # horizontal centralizer
                y_pdf_adjusted = y_pdf - text_height / 2  # vertical centralizer

                # safe border
                x_pdf_adjusted = max(0, min(x_pdf_adjusted, page_width - text_width))
                y_pdf_adjusted = max(0, min(y_pdf_adjusted, page_height - text_height))

                page.insert_text(
                    (x_pdf_adjusted, y_pdf_adjusted + ascender * font_size),
                    text,
                    fontsize=font_size,
                    color=rgb,
                    fontname="helv",
                )
                # # RECTANGLE FOR DEBUG
                # debug_rect = fitz.Rect(
                #     x_pdf_adjusted, y_pdf_adjusted,
                #     x_pdf_adjusted + text_width, y_pdf_adjusted + text_height
                # )
                # page.draw_rect(debug_rect, color=(1, 0, 0), width=0.3)

            temp_filename = f"dieta_personalizada_id_{diet.id}.pdf"
            temp_filepath = os.path.join(current_app.config["TEMP_UPLOAD_FOLDER"], temp_filename)
            doc.save(temp_filepath)
            doc.close()

            diet.temp_diet_file = temp_filename
            db.session.commit()

            return jsonify(
                {
                    "status": "success",
                    "message": "PDF atualizado com sucesso!",
                    "redirect_url": url_for("diets.list_diets"),
                }
            )
        except Exception as e:
            current_app.logger.error(f"Erro ao salvar PDF editado: {e}")
            return jsonify({"status": "error", "message": "Erro ao atualizar o PDF"}), 500

    pdf_url = url_for("diets.serve_file", filename=diet.diet_file, type_="temp", _external=True)
    return render_template("admin/diets/edit_diet.html", diet=diet, pdf_url=pdf_url)


@diets_bp.route("/diets/view_edited<int:id>", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_last_edition(id):
    diet = Diet.query.get_or_404(id)
    pdf_url = url_for("diets.serve_file", filename=diet.temp_diet_file, type_="temp", _external=True)
    return render_template("admin/diets/view_last_edition.html", diet=diet, pdf_url=pdf_url)
