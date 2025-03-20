import os
import re

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
from flask_security import current_user, roles_accepted
from twilio.base.exceptions import TwilioRestException
from werkzeug.utils import secure_filename

from app.forms import DietForm
from app.models import Diet, Patients, Specialists, db
from scripts.utils import twilio_send_diet

diets_bp = Blueprint("diets", __name__)


@diets_bp.route("/diets")
@roles_accepted("admin", "secretary", "nutritionist")
def list_diets():
    patients = Patients.query.all()
    if "nutritionist" in [role.name for role in current_user.roles]:
        patients = Patients.query.join(Specialists).filter(Specialists.email == current_user.email).all()

    diets = Diet.query.all()
    return render_template("admin/diets/list_diets.html", patients=patients, diets=diets)


@diets_bp.route("/diets/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_diet():
    form = DietForm()
    if form.validate_on_submit():
        pdf_filename = None
        if form.pdf_file.data:
            pdf_filename = secure_filename(form.pdf_file.data.filename)
            pdf_path = os.path.join(current_app.config["UPLOAD_FOLDER"], pdf_filename)
            form.pdf_file.data.save(pdf_path)

        diet_name = form.other_name.data if form.name.data == "Outro" else form.name.data
        diet = Diet(name=diet_name, description=form.description.data, pdf_file=pdf_filename)
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
        if diet.pdf_file:
            pdf_path = os.path.join(current_app.config["UPLOAD_FOLDER"], diet.pdf_file)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

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


@diets_bp.route("/send_diet/<int:diet_id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def send_diet(diet_id):
    patient = Patients.query.get_or_404(request.form.get("patient_id"))
    patient_name = patient.name
    cleaned_telephone = re.sub(r"[\s(),-]", "", patient.tel_number)
    if len(cleaned_telephone) == 11:
        telephone = f"+55{cleaned_telephone}"
    else:
        telephone = f"+55{cleaned_telephone[:2]}9{cleaned_telephone[2:len(cleaned_telephone)]}"

    diet = Diet.query.get_or_404(diet_id)
    if not diet.pdf_file:
        return jsonify({"error": "Essa dieta não possui um arquivo PDF"}), 400

    # Generating public URL for the PDF
    pdf_url = url_for("diets.serve_file", filename=diet.pdf_file, _external=True)
    try:
        # Send diet by WhatsApp
        response = twilio_send_diet(
            patient=patient_name,
            telephone=telephone,
            diet=diet.name,
            pdf_url=pdf_url,
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
