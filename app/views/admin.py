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
from app.models import Diet, Pacients, Role, User, db

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/create_user", methods=["GET", "POST"])
@roles_required("admin")
def create_user():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role") == "yes"
        if role:
            # Check if the role already exists, otherwise create it
            admin_role = Role.query.filter_by(name="admin").first()
            if not admin_role:
                admin_role = Role(name="admin")
                db.session.add(admin_role)
                db.session.commit()
        if not email or not password:
            return jsonify({"error": "Email e senha são obrigatórios!"}), 400

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Usuário já está cadastrado!"}), 400

        # Create new user
        user = User(email=email, active=True, password=hash_password(password), fs_uniquifier=uuid.uuid4().hex)
        if role:
            user.roles.append(admin_role)  # Assign the 'admin' role to the user

        db.session.add(user)
        db.session.commit()
        flash(f"Usuário {email} cadastrado com sucesso", "success")
        return render_template("/home.html")
    return render_template("/create_user.html")


@admin_bp.route("/pacients")
@roles_required("admin")
def list_pacients():
    pacients = Pacients.query.all()
    return render_template("admin/pacients/list_pacients.html", pacients=pacients)


@admin_bp.route("/pacients/add", methods=["GET", "POST"])
@roles_required("admin")
def add_pacient():
    pacients = Pacients.query.all()  # List of available pacients
    if request.method == "POST":
        try:
            pacient = Pacients(
                name=request.form.get("name"),
                gender=request.form.get("gender"),
                birth_date=datetime.strptime(request.form.get("birth_date"), "%Y-%m-%d").date(),
                cpf=request.form.get("cpf"),
                tel_number=request.form.get("phone"),
                email=request.form.get("email"),
                medication=request.form.get("medication"),
                medications_details=request.form.get("medications_details"),
                intestine=request.form.get("intestine"),
                allergies=request.form.get("allergies"),
                allergies_details=request.form.get("allergies_details"),
                water=request.form.get("water"),
                heartburn=request.form.get("heartburn"),
                physical_activities=request.form.get("physical_activities"),
                physical_details=request.form.get("physical_details"),
                hours=datetime.strptime(request.form.get("hours"), "%H:%M").time(),
                frequency=request.form.get("frequency"),
                objective=request.form.get("objective"),
                data_avaliacao=datetime.strptime(request.form.get("data_avaliacao"), "%Y-%m-%d").date(),
                idade=request.form.get("idade"),
                altura=request.form.get("altura"),
                peso=request.form.get("peso"),
                evolucao=request.form.get("evolucao"),
                p_max=request.form.get("p_max"),
                p_ide=request.form.get("p_ide"),
                p_min=request.form.get("p_min"),
                imc=request.form.get("imc"),
                nutri_class=request.form.get("nutri_class"),
                grau_atv_fisica=request.form.get("grau_atv_fisica"),
                pa=request.form.get("pa"),
                data_medicao=datetime.strptime(request.form.get("data_medicao"), "%Y-%m-%d").date(),
                triciptal=request.form.get("triciptal"),
                bicipital=request.form.get("bicipital"),
                subscapula=request.form.get("subscapula"),
                toracica=request.form.get("toracica"),
                axilar=request.form.get("axilar"),
                supra=request.form.get("supra"),
                abdominal=request.form.get("abdominal"),
                coxa=request.form.get("coxa"),
                panturrilha=request.form.get("panturrilha"),
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

    return render_template("admin/pacients/add_pacient.html", pacients=pacients)


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
    return render_template("admin/pacients/edit_pacient.html", form=form, pacient=pacient)


@admin_bp.route("/pacients/view/<int:id>", methods=["GET"])
@roles_required("admin")
def view_pacient(id):
    pacient = Pacients.query.get_or_404(id)
    return render_template("admin/pacients/view_pacient.html", pacient=pacient)


@admin_bp.route("/pacients/delete/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def delete_pacient(id):
    pacient = Pacients.query.get_or_404(id)
    if request.method == "POST":
        db.session.delete(pacient)
        db.session.commit()
        flash(f"Paciente '{pacient.name}' removido com sucesso!", "success")
        return redirect(url_for("admin.list_pacients"))
    return render_template("admin/pacients/delete_pacient.html", pacient=pacient)


@admin_bp.route("/diets")
@roles_required("admin")
def list_diets():
    diets = Diet.query.all()
    return render_template("admin/diets/list_diets.html", diets=diets)


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

    return render_template("admin/diets/add_diet.html", form=form)


@admin_bp.route("/diets/<int:id>", methods=["GET"])
@roles_required("admin")
def view_diet(id):
    diet = Diet.query.get_or_404(id)
    return render_template("admin/diets/view_diet.html", diet=diet)


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
    return render_template("admin/diets/delete_diet.html", diet=diet)


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
