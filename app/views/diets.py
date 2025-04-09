import os
import re
from datetime import datetime
from smtplib import SMTPAuthenticationError, SMTPSenderRefused
from zoneinfo import ZoneInfo

import pdfkit
from docx import Document
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_mail import Message
from flask_security import current_user, roles_accepted
from twilio.base.exceptions import TwilioRestException
from werkzeug.utils import secure_filename

from app.extensions import mail
from app.forms import DietForm
from app.models import Diet, Patients, Schedules, Specialists, db
from scripts.utils import twilio_send_diet

diets_bp = Blueprint("diets", __name__)


@diets_bp.route("/diets")
@roles_accepted("admin", "secretary", "nutritionist")
def list_diets():
    patients = Patients.query.all()
    if "nutritionist" in [role.name for role in current_user.roles]:
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
        patients = (
            Patients.query.join(Specialists, Patients.specialist_id == Specialists.id)  # Link Patients to Specialists
            .outerjoin(Schedules, Patients.id == Schedules.patient_id)  # Outer Linking Patients to Schedules
            .filter(
                (Specialists.email == current_user.email)
                | (  # Getting only Nutri's Patients
                    (Schedules.specialist == current_user.username) & (Schedules.date_time >= now)
                )  # And her external appointments
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
    return render_template("admin/diets/view_diet.html", diet=diet)


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

        # Remove from database
        db.session.delete(diet)
        db.session.commit()
        flash(f"Dieta '{diet.name}' removida com sucesso!", "success")
        return redirect(url_for("diets.list_diets"))
    return render_template("admin/diets/delete_diet.html", diet=diet)


@diets_bp.route("/diets/download/<filename>")
@roles_accepted("admin", "secretary", "nutritionist")
def download_diet(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@diets_bp.route("/send_diet_email/<int:diet_id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def send_diet_email(diet_id):
    patient = Patients.query.get_or_404(request.form.get("patient_id"))
    patient_name = patient.name

    if not patient.email:
        flash(f"O paciente {patient_name} não possui email cadastrado.", "danger")
        return redirect(url_for("diets.list_diets"))

    diet = Diet.query.get_or_404(diet_id)
    if not diet.diet_file:
        flash("Essa dieta não possui um arquivo.", "danger")
        return redirect(url_for("diets.list_diets"))

    # Generating public URL for the File
    diet_file_url = url_for("diets.serve_file", filename=diet.diet_file, _external=True)

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

    diet_file_path = os.path.join(current_app.config.get("UPLOAD_FOLDER"), diet.diet_file)
    if not os.path.exists(diet_file_path):
        flash("Arquivo não encontrado no servidor.", "danger")
        return redirect(url_for("diets.list_diets"))
    try:
        with current_app.open_resource(diet_file_path, "rb") as fp:
            diet_file_data = fp.read()
            msg.attach(filename=diet.diet_file, content_type="application/pdf", data=diet_file_data)

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
    if not diet.diet_file:
        flash("Essa dieta não possui um arquivo.", "danger")
        return redirect(url_for("diets.list_diets"))

    # Generating public URL for the File
    diet_file_url = url_for("diets.serve_file", filename=diet.diet_file, _external=True)
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
            f"Dieta '{diet.name}' enviada com sucesso para o paciente '{patient_name}'! "
            f"ID de Confirmação: '{response}'",
            "success",
        )
        return redirect(url_for("diets.list_diets"))
    except TwilioRestException:
        flash("Não foi possível enviar a dieta com sucesso. Consulte o suporte!", "danger")
        return redirect(url_for("diets.list_diets"))


@diets_bp.route("/uploads/<filename>")
def serve_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@diets_bp.route("/diets/edit/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_diet(id):
    diet = Diet.query.get_or_404(id)
    # Verifica se o arquivo existe e se é do tipo Word (você pode fazer uma verificação pela extensão)
    if diet.diet_file and diet.diet_file.lower().endswith((".doc", ".docx")):
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], diet.diet_file)
        try:
            document = Document(file_path)
            # Extrai todo o texto do documento
            content = "\n".join([para.text for para in document.paragraphs])
        except Exception as err:
            flash(f"Erro ao ler o arquivo Word. {err}", "danger")
            return redirect(url_for("diets.list_diets"))
    else:
        flash("Arquivo não é um documento Word.", "danger")
        return redirect(url_for("diets.list_diets"))

    # Se o método for POST, processa o formulário
    if request.method == "POST":
        if "save" in request.form:
            edited_text = request.form.get("content")
            # Gere um novo nome para o arquivo PDF, por exemplo:
            pdf_filename = secure_filename(f"{diet.name}_editado.pdf")
            pdf_path = os.path.join(current_app.config["UPLOAD_FOLDER"], pdf_filename)
            try:
                # Exemplo: usando pdfkit (ou outra biblioteca) para converter o texto em PDF.
                # Para pdfkit, você pode gerar um HTML simples com o conteúdo.
                html_content = f"<html><body><pre>{edited_text}</pre></body></html>"
                pdfkit.from_string(html_content, pdf_path)
                # Atualize o registro para usar o PDF editado
                diet.diet_file = pdf_filename
                db.session.commit()
                flash("Arquivo editado e salvo como PDF com sucesso!", "success")
            except Exception as e:
                current_app.logger.error(f"Erro ao converter para PDF: {e}")
                flash("Erro ao salvar as alterações.", "danger")
            return redirect(url_for("diets.list_diets"))
        elif "discard" in request.form:
            flash("Alterações descartadas.", "info")
            return redirect(url_for("diets.list_diets"))

    # Exibe a página de edição
    return render_template("admin/diets/edit_diet.html", diet=diet, content=content)
