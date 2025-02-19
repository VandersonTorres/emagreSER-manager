import os
import uuid
from datetime import datetime

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
from flask_security import roles_required
from flask_security.utils import hash_password
from sqlalchemy.exc import IntegrityError
from twilio.rest import Client
from werkzeug.utils import secure_filename

from app.forms import DietForm, PacientForm
from app.models import Diet, Pacients, User, db

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/create_user", methods=["POST"])
@roles_required("admin")
def create_user():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email e senha são obrigatórios!"}), 400

    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "Usuário já está cadastrado!"}), 400

    # Create new user
    user = User(email=email, active=True, password=hash_password(password), fs_uniquifier=uuid.uuid4().hex)

    db.session.add(user)
    db.session.commit()
    return jsonify({"message": f"Usuário {email} cadastrado com sucesso"}), 201


@admin_bp.route("/pacients")
@roles_required("admin")
def list_pacients():
    pacients = Pacients.query.all()
    return render_template("admin/list_pacients.html", pacients=pacients)


@admin_bp.route("/pacients/add", methods=["GET", "POST"])
@roles_required("admin")
def add_pacient():
    pacients = Pacients.query.all()  # List of available pacients
    if request.method == "POST":
        try:
            pacient = Pacients(
                name=request.form["name"],
                gender=request.form["gender"],
                birth_date=datetime.strptime(request.form.get("birth_date"), "%Y-%m-%d").date(),
                cpf=request.form["cpf"],
                tel_number=request.form["phone"],
                email=request.form["email"],
                medication=request.form["medication"],
                medications_details=request.form["medications_details"],
                intestine=request.form["intestine"],
                allergies=request.form["allergies"],
                allergies_details=request.form["allergies_details"],
                water=request.form["water"],
                heartburn=request.form["heartburn"],
                physical_activities=request.form["physical_activities"],
                physical_details=request.form["physical_details"],
                hours=datetime.strptime(request.form["hours"], "%H:%M").time(),
                frequency=request.form["frequency"],
                objective=request.form["objective"],
                data_avaliacao=datetime.strptime(request.form.get("data_avaliacao"), "%Y-%m-%d").date(),
                idade=request.form["idade"],
                altura=request.form["altura"],
                peso=request.form["peso"],
                evolucao=request.form["evolucao"],
                p_max=request.form["p_max"],
                p_ide=request.form["p_ide"],
                p_min=request.form["p_min"],
                imc=request.form["imc"],
                nutri_class=request.form["nutri_class"],
                grau_atv_fisica=request.form["grau_atv_fisica"],
                pa=request.form["pa"],
                data_medicao=datetime.strptime(request.form.get("data_medicao"), "%Y-%m-%d").date(),
                triciptal=request.form["triciptal"],
                bicipital=request.form["bicipital"],
                subscapula=request.form["subscapula"],
                toracica=request.form["toracica"],
                axilar=request.form["axilar"],
                supra=request.form["supra"],
                abdominal=request.form["abdominal"],
                coxa=request.form["coxa"],
                panturrilha=request.form["panturrilha"],
            )

            db.session.add(pacient)
            db.session.commit()
            flash("Paciente cadastrado com sucesso!", "success")
            return redirect(url_for("admin.list_pacients"))
        except IntegrityError as e:
            db.session.rollback()
            error_message = e
            if "pacients.name" in str(e):
                error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
            elif "pacients.cpf" in str(e):
                error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

            flash(error_message, "danger")

    return render_template("admin/add_pacient.html", pacients=pacients)


@admin_bp.route("/pacients/edit/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def edit_pacient(id):
    pacient = Pacients.query.get_or_404(id)
    form = PacientForm(obj=pacient)
    if request.method == "POST":
        try:
            form.populate_obj(pacient)
            db.session.commit()
            flash(f"Dados do paciente '{pacient.name}' atualizados com sucesso!", "success")
            return redirect(url_for("admin.list_pacients"))
        except IntegrityError as e:
            db.session.rollback()
            error_message = e
            if "pacients.name" in str(e):
                error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
            elif "pacients.cpf" in str(e):
                error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

            flash(error_message, "danger")
    return render_template("admin/edit_pacient.html", form=form, pacient=pacient)


@admin_bp.route("/pacients/view/<int:id>", methods=["GET"])
@roles_required("admin")
def view_pacient(id):
    pacient = Pacients.query.get_or_404(id)
    return render_template("admin/view_pacient.html", pacient=pacient)


@admin_bp.route("/pacients/delete/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def delete_pacient(id):
    pacient = Pacients.query.get_or_404(id)
    if request.method == "POST":
        db.session.delete(pacient)
        db.session.commit()
        flash(f"Paciente '{pacient.name}' removido com sucesso!", "success")
        return redirect(url_for("admin.list_pacients"))
    return render_template("admin/delete_pacient.html", pacient=pacient)


@admin_bp.route("/diets")
@roles_required("admin")
def list_diets():
    diets = Diet.query.all()
    return render_template("admin/list_diets.html", diets=diets)


@admin_bp.route("/diets/add", methods=["GET", "POST"])
@roles_required("admin")
def add_diet():
    form = DietForm()
    if form.validate_on_submit():
        pdf_filename = None
        if form.pdf_file.data:
            pdf_filename = secure_filename(form.pdf_file.data.filename)
            pdf_path = os.path.join(current_app.config["UPLOAD_FOLDER"], pdf_filename)
            form.pdf_file.data.save(pdf_path)

        diet_name = form.other_name.data if form.name.data == "outro" else form.name.data
        diet = Diet(name=diet_name, description=form.description.data, pdf_file=pdf_filename)
        db.session.add(diet)
        db.session.commit()

        flash("Dieta cadastrada com sucesso!")
        return redirect(url_for("admin.list_diets"))

    return render_template("admin/add_diet.html", form=form)


@admin_bp.route("/diets/<int:id>", methods=["GET"])
@roles_required("admin")
def view_diet(id):
    diet = Diet.query.get_or_404(id)
    return render_template("admin/view_diet.html", diet=diet)


@admin_bp.route("/diets/delete/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
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
        return redirect(url_for("admin.list_diets"))
    return render_template("admin/delete_diet.html", diet=diet)


@admin_bp.route("/diets/download/<filename>")
@roles_required("admin")
def download_diet(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@admin_bp.route("/send_diet/<int:diet_id>", methods=["POST"])
@roles_required("admin")
def send_diet(diet_id):
    def twilio_send_diet(pacient, telephone, diet):
        client = Client(current_app.config["TWILIO_SID"], current_app.config["TWILIO_AUTH"])
        message = f"Olá {pacient}, aqui está sua dieta:\n{diet}"
        client.messages.create(body=message, from_=current_app.config["TWILIO_PHONE"], to=telephone)

    telephone = request.form.get("telefone")
    if not telephone:
        return jsonify({"error": "Número de telefone é obrigatório"}), 400

    diet = Diet.query.get_or_404(diet_id)
    if not diet.pdf_file:
        return jsonify({"error": "Essa dieta não possui um arquivo PDF"}), 400

    # Send diet by WhatsApp
    response = twilio_send_diet(
        pacient="Paciente", telephone=telephone, diet_name=diet.name, pdf_filename=diet.pdf_file
    )

    return jsonify({"message": response}), 200
