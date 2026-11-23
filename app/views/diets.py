import os
import re
from datetime import datetime
from smtplib import SMTPAuthenticationError, SMTPSenderRefused
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

import cloudinary
import cloudinary.uploader
import fitz
import requests
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
from flask.typing import ResponseReturnValue
from flask_mail import Message
from flask_security import current_user, roles_accepted
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from twilio.base.exceptions import TwilioRestException
from werkzeug.utils import secure_filename
from werkzeug.wrappers import Response

from app.extensions import mail
from app.forms import DietForm
from app.models import Diet, Patients, Schedules, Specialists, db
from app.services.pdf_annotations import apply_annotations
from scripts.utils import extract_public_id_from_cloudinary, twilio_send_diet

diets_bp = Blueprint("diets", __name__)


@diets_bp.route("/diets")
@roles_accepted("admin", "secretary", "nutritionist")
def list_diets() -> ResponseReturnValue:
    """Render the list of diets, filtered by the optional "query" argument.

    Nutritionists only see, in the patient selector, the patients of their own or with a pending schedule with them.

    :return: The rendered diets page.
    """
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

    search_query = request.args.get("query", "").strip()
    if search_query:
        diets = (
            Diet.query.filter(Diet.name.ilike(f"%{search_query}%")).order_by(Diet.order.asc(), Diet.name.asc()).all()
        )
    else:
        diets = Diet.query.order_by(Diet.order.asc(), Diet.name.asc()).all()

    return render_template("admin/diets/list_diets.html", patients=patients, diets=diets, search_query=search_query)


@diets_bp.route("/diets/reorder", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def reorder_diets() -> ResponseReturnValue:
    """Store the new position of each diet sent as JSON in "order".

    :return: A JSON confirmation.
    """
    data = request.get_json()
    order_data = data.get("order", [])

    for item in order_data:
        diet = Diet.query.get(item["id"])
        if diet:
            diet.order = item["position"]

    db.session.commit()
    return jsonify({"status": "success", "message": "Ordem atualizada"})


@diets_bp.route("/diets/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_diet() -> ResponseReturnValue:
    """Show the form to register a diet and, on a valid submission, upload its PDF and save it.

    :return: The form page, or a redirect to the diet list after saving.
    """
    form = DietForm()
    if form.validate_on_submit():
        diet_url = None
        if form.diet_file.data:
            original_filename = os.path.splitext(secure_filename(form.diet_file.data.filename))[0]
            upload_result = cloudinary.uploader.upload(
                form.diet_file.data, resource_type="raw", folder="diets", public_id=original_filename, overwrite=True
            )
            diet_url = upload_result["secure_url"]

        diet_name = form.other_name.data if form.name.data == "Outro" else form.name.data
        diet = Diet(name=diet_name, description=form.description.data, diet_file=diet_url)
        db.session.add(diet)
        db.session.commit()

        flash("Dieta cadastrada com sucesso!")
        return redirect(url_for("diets.list_diets"))

    return render_template("admin/diets/add_diet.html", form=form)


@diets_bp.route("/diets/<int:id>", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_diet(id: int) -> ResponseReturnValue:
    """Render the original PDF of a diet.

    :param id: Id of the diet.
    :raises NotFound: If the diet does not exist.
    :return: The rendered diet page.
    """
    diet = Diet.query.get_or_404(id)
    return render_template("admin/diets/view_diet.html", diet=diet, pdf_url=diet.diet_file)


@diets_bp.route("/diets/delete/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_diet(id: int) -> ResponseReturnValue:
    """Ask for confirmation and, on POST, delete the diet with its stored and edited PDF files.

    :param id: Id of the diet.
    :raises NotFound: If the diet does not exist.
    :return: The confirmation page, or a redirect to the diet list after deleting.
    """
    diet = Diet.query.get_or_404(id)
    if request.method == "POST":
        if diet.diet_file:
            public_id = extract_public_id_from_cloudinary(diet.diet_file)
            cloudinary.uploader.destroy(public_id, resource_type="raw")

        if diet.temp_diet_file:
            temp_diet_file_path = os.path.join(current_app.config["TEMP_UPLOAD_FOLDER"], diet.temp_diet_file)
            if os.path.exists(temp_diet_file_path):
                os.remove(temp_diet_file_path)

        db.session.delete(diet)
        db.session.commit()
        flash(f"Dieta '{diet.name}' removida com sucesso!", "success")
        return redirect(url_for("diets.list_diets"))
    return render_template("admin/diets/delete_diet.html", diet=diet)


@diets_bp.route("/uploads/temp_files/<filename>")
def serve_temp_file(filename: str) -> Response:
    """Serve an edited diet PDF from the temporary folder; public on purpose, so Twilio can fetch it.

    :param filename: Name of the file inside the temporary folder.
    :return: The file response.
    """
    return send_from_directory(current_app.config["TEMP_UPLOAD_FOLDER"], filename)


@diets_bp.route("/diets/download-temp/<filename>")
@roles_accepted("admin", "secretary", "nutritionist")
def download_temp_diet(filename: str) -> Response:
    """Send an edited diet PDF from the temporary folder as an attachment.

    :param filename: Name of the file inside the temporary folder.
    :return: The file response, as an attachment.
    """
    folder = current_app.config["TEMP_UPLOAD_FOLDER"]
    return send_from_directory(folder, filename, as_attachment=True)


@diets_bp.route("/send_diet_email/<int:diet_id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def send_diet_email(diet_id: int) -> ResponseReturnValue:
    """E-mail the last edited PDF of a diet to the patient chosen in the form.

    :param diet_id: Id of the diet.
    :raises NotFound: If the patient or the diet does not exist.
    :return: A redirect to the diet list, with a flashed result.
    """
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

    msg = Message(
        subject=f"Dieta {diet.name}", recipients=[patient.email], sender=current_app.config.get("MAIL_DEFAULT_SENDER")
    )
    msg.charset = "utf-8"
    msg.body = (
        f"Olá, {patient_name},\n\n"
        f"Segue a sua dieta '{diet.name}' dessa semana.\n"
        f"Você pode acessar e baixar o arquivo em anexo.\n"
        "Se tiver dúvidas não se preocupe, entre em contato conosco!\n\n"
        "At.te, Equipe EmagreSER\n"
        "+55 (31) 9 9668-4161"
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
def send_diet_wpp(diet_id: int) -> ResponseReturnValue:
    """Send the last edited PDF of a diet by WhatsApp to the patient chosen in the form.

    :param diet_id: Id of the diet.
    :raises NotFound: If the patient or the diet does not exist.
    :return: A redirect to the diet list, with a flashed result.
    """
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

    diet_file_url = url_for("diets.serve_temp_file", filename=temp_diet_file, _external=True)
    try:
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


@diets_bp.route("/diets/edit_diet/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_diet(id: int) -> ResponseReturnValue:
    """Show the PDF editor of a diet and, on POST, write the posted annotations into a copy of its PDF.

    GET renders the current editor, or the previous one with "?legacy=1". POST downloads the original PDF, applies the
    annotations, saves the result as the diet's temporary file and answers with JSON (status, message, URLs).

    :param id: Id of the diet.
    :raises NotFound: If the diet does not exist.
    :return: The editor page, a redirect to the diet list when the diet has no file, or the JSON answer of the save.
    """
    diet = Diet.query.get_or_404(id)
    if not diet.diet_file:
        flash("Essa dieta não possui um arquivo.", "danger")
        return redirect(url_for("diets.list_diets"))

    if request.method == "POST":
        try:
            annotations = request.json.get("annotations")
            if not annotations:
                return jsonify({"status": "error", "message": "Não foi possível detectar alterações"}), 400

            response = requests.get(diet.diet_file)
            if response.status_code != 200:
                current_app.logger.error(f"Erro ao baixar o PDF do Cloudinary: {response.text}")
                raise Exception("Erro ao baixar o PDF do Cloudinary")

            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
                tmp_in.write(response.content)
                tmp_in.flush()
                doc = fitz.open(tmp_in.name)

            apply_annotations(doc, annotations, current_app.logger)

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
                    "download_url": url_for("diets.download_temp_diet", filename=temp_filename),
                }
            )
        except Exception as e:
            current_app.logger.error(f"Erro ao salvar PDF editado: {e}")
            return jsonify({"status": "error", "message": "Erro ao atualizar o PDF"}), 500

    use_legacy = request.args.get("legacy") == "1"
    template = "admin/diets/edit_diet_legacy.html" if use_legacy else "admin/diets/edit_diet.html"
    return render_template(template, diet=diet, pdf_url=diet.diet_file)


@diets_bp.route("/diets/edit/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_diet_raw(id: int) -> ResponseReturnValue:
    """Show the form to change the name, description and PDF of a diet and save it when valid.

    :param id: Id of the diet.
    :raises NotFound: If the diet does not exist.
    :return: The form page, or a redirect to the diet list after saving.
    """
    diet = Diet.query.get_or_404(id)
    form = DietForm(obj=diet)

    if form.validate_on_submit():
        try:
            diet_name = form.other_name.data if form.name.data == "Outro" else form.name.data
            diet.name = diet_name
            diet.description = form.description.data

            if form.diet_file.data:
                original_filename = os.path.splitext(secure_filename(form.diet_file.data.filename))[0]
                upload_result = cloudinary.uploader.upload(
                    form.diet_file.data,
                    resource_type="raw",
                    folder="diets",
                    public_id=original_filename,
                    overwrite=True,
                )
                diet.diet_file = upload_result["secure_url"]

            db.session.commit()
            flash(f"Dieta '{diet.name}' atualizada com sucesso!", "success")
            return redirect(url_for("diets.list_diets"))
        except IntegrityError as e:
            db.session.rollback()
            error_message = str(e)
            if "diets.name" in error_message:
                error_message = "Erro: Já existe uma dieta com esse nome cadastrada!"
            flash(error_message, "danger")

    return render_template("admin/diets/edit_diet_raw.html", form=form, diet=diet)


@diets_bp.route("/diets/view_edited<int:id>", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_last_edition(id: int) -> ResponseReturnValue:
    """Render the last edited PDF of a diet, or an empty state when the diet was never edited.

    :param id: Id of the diet.
    :raises NotFound: If the diet does not exist.
    :return: The rendered page.
    """
    diet = Diet.query.get_or_404(id)
    pdf_url = None
    if diet.temp_diet_file:
        pdf_url = url_for("diets.serve_temp_file", filename=diet.temp_diet_file)
    return render_template("admin/diets/view_last_edition.html", diet=diet, pdf_url=pdf_url)
