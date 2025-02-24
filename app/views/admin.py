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

from app.forms import AnthropometricAssessmentForm, DietForm, PatientForm, SkinfoldMeasurementForm
from app.models import AnthropometricEvaluation, Diet, Patients, Role, SkinFolds, User, db

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


@admin_bp.route("/users")
@roles_required("admin")
def list_users():
    users = User.query.all()
    return render_template("list_users.html", users=users)


@admin_bp.route("/users/delete/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def delete_user(id):
    user = User.query.get_or_404(id)
    if request.method == "POST":
        db.session.delete(user)
        db.session.commit()
        flash(f"Usuário '{user.email}' removido com sucesso!", "success")
        return redirect(url_for("admin.list_users"))
    return render_template("delete_user.html", user=user)


@admin_bp.route("/patients")
@roles_required("admin")
def list_patients():
    patients = Patients.query.all()
    return render_template("admin/patients/list_patients.html", patients=patients)


@admin_bp.route("/patients/add", methods=["GET", "POST"])
@roles_required("admin")
def add_patient():
    if request.method == "POST":
        try:
            patient = Patients(
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
                hours=datetime.strptime(request.form.get("hours"), "%H:%M").time()
                if request.form.get("hours")
                else None,
                frequency=request.form.get("frequency"),
                objective=request.form.get("objective"),
            )

            db.session.add(patient)
            db.session.commit()
            flash("Paciente cadastrado com sucesso!", "success")
            return redirect(url_for("admin.list_patients"))
        except IntegrityError as e:
            db.session.rollback()
            field_name = str(e).split("UNIQUE constraint failed: ")[1].split(" ")[0]
            error_message = (
                f"Erro ao cadastrar paciente. O seguinte campo já foi atribuído à outro paciente: {field_name}"
            )

            if "patients.name" in str(e):
                error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
            elif "patients.cpf" in str(e):
                error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

            flash(error_message, "danger")

    return render_template("admin/patients/add_patient.html")


@admin_bp.route("/patients/<int:patient_id>/anthropometric/add", methods=["GET", "POST"])
@roles_required("admin")
def add_anthro(patient_id):
    patient = Patients.query.get_or_404(patient_id)
    form = AnthropometricAssessmentForm()
    diet_form = DietForm()
    diet_form.name.data = form.ultima_guia.data
    # Search for the last evaluation of the patient (except the current, if there was one)
    previous_anthro = (
        AnthropometricEvaluation.query.filter_by(patient_id=patient.id)
        .order_by(AnthropometricEvaluation.data_avaliacao.desc())
        .first()
    )
    peso_anterior = previous_anthro.peso if previous_anthro else 0
    if form.validate_on_submit():
        diet_name = diet_form.other_name.data if diet_form.name.data == "outro" else diet_form.name.data
        form.ultima_guia.data = diet_name
        anthro = AnthropometricEvaluation(
            patient_id=patient.id,
            data_avaliacao=form.data_avaliacao.data,
            ultima_guia=form.ultima_guia.data,
            idade=form.idade.data,
            altura=form.altura.data,
            peso=form.peso.data,
            evolucao=form.evolucao.data,
            p_max=form.p_max.data,
            p_ide=form.p_ide.data,
            p_min=form.p_min.data,
            imc=form.imc.data,
            nutri_class=form.nutri_class.data,
            grau_atv_fisica=form.grau_atv_fisica.data,
            pa=form.pa.data,
        )
        db.session.add(anthro)
        db.session.commit()
        flash("Avaliação antropométrica adicionada com sucesso!", "success")
        return redirect(url_for("admin.view_patient", id=patient.id))
    return render_template(
        "admin/patients/add_anthro.html", form=form, diet_form=diet_form, patient=patient, peso_anterior=peso_anterior
    )


@admin_bp.route("/patients/<int:patient_id>/skinfolds/add", methods=["GET", "POST"])
@roles_required("admin")
def add_skinfold(patient_id):
    patient = Patients.query.get_or_404(patient_id)
    form = SkinfoldMeasurementForm()
    if form.validate_on_submit():
        skinfold = SkinFolds(
            patient_id=patient.id,
            data_medicao=form.data_medicao.data,
            triciptal=form.triciptal.data,
            bicipital=form.bicipital.data,
            subscapula=form.subscapula.data,
            toracica=form.toracica.data,
            axilar=form.axilar.data,
            supra=form.supra.data,
            abdominal=form.abdominal.data,
            coxa=form.coxa.data,
            panturrilha=form.panturrilha.data,
        )
        db.session.add(skinfold)
        db.session.commit()
        flash("Pregas cutâneas adicionadas com sucesso!", "success")
        return redirect(url_for("admin.view_patient", id=patient.id))
    return render_template("admin/patients/add_skinfold.html", form=form, patient=patient)


@admin_bp.route("/patients/edit/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def edit_patient(id):
    patient = Patients.query.get_or_404(id)
    form = PatientForm(obj=patient)
    if request.method == "POST":
        try:
            if form.frequency.data is None:
                # Even defining a default value in the model,
                # SQL doesn't considere this in UPDATE operations
                form.frequency.data = 0
            form.populate_obj(patient)
            db.session.commit()
            flash(f"Dados do paciente '{patient.name}' atualizados com sucesso!", "success")
            return redirect(url_for("admin.list_patients"))
        except IntegrityError as e:
            db.session.rollback()
            error_message = str(e)
            if "patients.name" in str(e):
                error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
            elif "patients.cpf" in str(e):
                error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

            flash(error_message, "danger")
    return render_template("admin/patients/edit_patient.html", form=form, patient=patient)


@admin_bp.route("/patients/<int:patient_id>/anthro/edit/<int:evaluation_id>", methods=["GET", "POST"])
@roles_required("admin")
def edit_anthro(patient_id, evaluation_id):
    evaluation = AnthropometricEvaluation.query.get_or_404(evaluation_id)
    form = AnthropometricAssessmentForm(obj=evaluation)
    diet_form = DietForm(name=evaluation.ultima_guia)
    if form.validate_on_submit():
        diet_name = diet_form.other_name.data if diet_form.name.data == "outro" else diet_form.name.data
        form.populate_obj(evaluation)
        evaluation.ultima_guia = diet_name
        db.session.commit()
        flash("Avaliação antropométrica atualizada com sucesso!", "success")
        return redirect(url_for("admin.view_patient", id=patient_id))
    return render_template("admin/patients/edit_anthro.html", form=form, diet_form=diet_form, evaluation=evaluation)


@admin_bp.route("/patients/<int:patient_id>/skinfolds/edit/<int:skinfold_id>", methods=["GET", "POST"])
@roles_required("admin")
def edit_skinfold(patient_id, skinfold_id):
    skinfold = SkinFolds.query.get_or_404(skinfold_id)
    form = SkinfoldMeasurementForm(obj=skinfold)
    if form.validate_on_submit():
        form.populate_obj(skinfold)
        db.session.commit()
        flash("Dados de pregas cutâneas atualizados com sucesso!", "success")
        return redirect(url_for("admin.view_patient", id=patient_id))
    return render_template("admin/patients/edit_skinfold.html", form=form, skinfold=skinfold)


@admin_bp.route("/patients/view/<int:id>", methods=["GET"])
@roles_required("admin")
def view_patient(id):
    patient = Patients.query.get_or_404(id)
    return render_template("admin/patients/view_patient.html", patient=patient)


@admin_bp.route("/patients/delete/<int:id>", methods=["GET", "POST"])
@roles_required("admin")
def delete_patient(id):
    patient = Patients.query.get_or_404(id)
    if request.method == "POST":
        for schedule in patient.schedules:
            db.session.delete(schedule)
        for evaluation in patient.anthropometric_evaluations:
            db.session.delete(evaluation)
        for skinfold in patient.skinfolds:
            db.session.delete(skinfold)
        db.session.delete(patient)
        db.session.commit()
        flash(f"Paciente '{patient.name}' removido com sucesso!", "success")
        return redirect(url_for("admin.list_patients"))
    return render_template("admin/patients/delete_patient.html", patient=patient)


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
    def twilio_send_diet(patient, telephone, diet):
        client = Client(current_app.config["TWILIO_SID"], current_app.config["TWILIO_AUTH"])
        message = f"Olá {patient}, aqui está sua dieta:\n{diet}"
        client.messages.create(body=message, from_=current_app.config["TWILIO_PHONE"], to=telephone)

    telephone = request.form.get("telefone")
    if not telephone:
        return jsonify({"error": "Número de telefone é obrigatório"}), 400

    diet = Diet.query.get_or_404(diet_id)
    if not diet.pdf_file:
        return jsonify({"error": "Essa dieta não possui um arquivo PDF"}), 400

    # Send diet by WhatsApp
    response = twilio_send_diet(
        patient="Paciente", telephone=telephone, diet_name=diet.name, pdf_filename=diet.pdf_file
    )

    return jsonify({"message": response}), 200
