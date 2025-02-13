import os
import uuid

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

from app.forms import DietForm
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
        name = request.form["name"]
        cpf = request.form["cpf"]
        tel_number = request.form["phone"]
        try:
            # Add the pacient
            pacient = Pacients(name=name, cpf=cpf, tel_number=tel_number)
            db.session.add(pacient)
            db.session.commit()
            flash("Paciente cadastrado com sucesso!", "success")
            return redirect(url_for("admin.list_pacients"))
        except IntegrityError as e:
            db.session.rollback()
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
    if request.method == "POST":
        try:
            pacient.name = request.form["name"]
            pacient.cpf = request.form["cpf"]
            pacient.tel_number = request.form["tel_number"]
            db.session.commit()
            flash(f"Dados do paciente '{pacient.name}' atualizados com sucesso!", "success")
            return redirect(url_for("admin.list_pacients"))
        except IntegrityError as e:
            db.session.rollback()
            if "pacients.name" in str(e):
                error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
            elif "pacients.cpf" in str(e):
                error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

            flash(error_message, "danger")
    return render_template("admin/edit_pacient.html", pacient=pacient)


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

        diet = Diet(name=form.name.data, description=form.description.data, pdf_file=pdf_filename)
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
