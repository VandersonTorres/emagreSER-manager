from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_security import current_user, roles_accepted
from sqlalchemy.exc import IntegrityError

from app.forms import AnthropometricAssessmentForm, DietForm, PatientForm, SkinfoldMeasurementForm
from app.models import AnthropometricEvaluation, Patients, Schedules, SkinFolds, Specialists, db
from scripts.utils import block_access_to_patients

patients_bp = Blueprint("patients", __name__)


@patients_bp.route("/patients")
@roles_accepted("admin", "secretary", "nutritionist")
def list_patients():
    if "nutritionist" in [role.name for role in current_user.roles]:
        now = datetime.now()
        patients = (
            Patients.query.join(Schedules, Patients.id == Schedules.patient_id)
            .filter(Schedules.specialist == current_user.username, Schedules.date_time >= now)
            .distinct()
            .all()
        )
    else:
        patients = Patients.query.all()
    return render_template("admin/patients/list_patients.html", patients=patients)


@patients_bp.route("/patients/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_patient():
    specialists = Specialists.query.all()
    if request.method == "POST":
        try:
            patient = Patients(
                name=request.form.get("name"),
                gender=request.form.get("gender"),
                birth_date=datetime.strptime(request.form.get("birth_date"), "%Y-%m-%d").date(),
                cpf=request.form.get("cpf"),
                tel_number=request.form.get("phone"),
                email=request.form.get("email"),
                specialist_id=request.form.get("specialist"),
                medication=request.form.get("medication"),
                medications_details=request.form.get("medications_details"),
                intestine=request.form.get("intestine"),
                allergies=request.form.get("allergies"),
                allergies_details=request.form.get("allergies_details"),
                water=request.form.get("water"),
                heartburn=request.form.get("heartburn"),
                physical_activities=request.form.get("physical_activities"),
                physical_details=request.form.get("physical_details"),
                hours=(
                    datetime.strptime(request.form.get("hours"), "%H:%M").time() if request.form.get("hours") else None
                ),
                frequency=request.form.get("frequency"),
                objective=request.form.get("objective"),
            )

            db.session.add(patient)
            db.session.commit()
            flash("Paciente cadastrado com sucesso!", "success")
            return redirect(url_for("patients.list_patients"))
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
        except Exception as e:
            flash(f"Ocorreu o seguinte erro ao tentar cadastrar o paciente: {e}")

    return render_template("admin/patients/add_patient.html", specialists=specialists)


@patients_bp.route("/patients/<int:patient_id>/anthropometric/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_anthro(patient_id):
    patient = Patients.query.get_or_404(patient_id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode adicionar dados para os seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
        form = AnthropometricAssessmentForm()
        diet_form = DietForm()
        diet_form.name.data = form.ultima_guia.data
        # Search for the last evaluation of the patient (except the current, if there was one)
        last_skinfold = SkinFolds.query.filter_by(patient_id=patient.id).order_by(SkinFolds.data_medicao.desc()).first()

        if last_skinfold:
            ultimo_peso = last_skinfold.peso
            ultima_altura = last_skinfold.altura
            evaluation_date = last_skinfold.data_medicao
            # Searching for the previous record to last weight
            previous_skinfold = (
                SkinFolds.query.filter(
                    SkinFolds.patient_id == patient.id, SkinFolds.data_medicao < last_skinfold.data_medicao
                )
                .order_by(SkinFolds.data_medicao.desc())
                .first()
            )
            peso_anterior = previous_skinfold.peso if previous_skinfold else 0
        else:
            ultimo_peso = 0
            peso_anterior = 0
            ultima_altura = 0
            evaluation_date = ""
        if form.validate_on_submit():
            diet_name = diet_form.other_name.data if diet_form.name.data == "outro" else diet_form.name.data
            form.ultima_guia.data = diet_name
            anthro = AnthropometricEvaluation(
                patient_id=patient.id,
                data_avaliacao=form.data_avaliacao.data,
                ultima_guia=form.ultima_guia.data,
                idade=form.idade.data,
                evolucao=form.evolucao.data,
                p_max=form.p_max.data,
                p_ide=form.p_ide.data,
                p_min=form.p_min.data,
                imc=form.imc.data,
                nutri_class=form.nutri_class.data,
                necessidade_calorica=form.necessidade_calorica.data,
                ingestao_liquido=form.ingestao_liquido.data,
                grau_atv_fisica=form.grau_atv_fisica.data,
                pa=form.pa.data,
                specialist_name=current_user.username,
            )
            db.session.add(anthro)
            db.session.commit()
            flash("Avaliação antropométrica adicionada com sucesso!", "success")
            return redirect(url_for("patients.view_patient", id=patient.id))
        return render_template(
            "admin/patients/add_anthro.html",
            form=form,
            diet_form=diet_form,
            patient=patient,
            peso_anterior=peso_anterior,
            ultimo_peso=ultimo_peso,
            ultima_altura=ultima_altura,
            evaluation_date=evaluation_date,
        )


@patients_bp.route("/patients/<int:patient_id>/skinfolds/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_skinfold(patient_id):
    patient = Patients.query.get_or_404(patient_id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode adicionar dados para os seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
        last_patient_height = patient.skinfolds[-1].altura if len(patient.skinfolds) else None
        form = SkinfoldMeasurementForm()
        if form.validate_on_submit():
            skinfold = SkinFolds(
                patient_id=patient.id,
                data_medicao=form.data_medicao.data,
                altura=last_patient_height if last_patient_height else form.altura.data,
                peso=form.peso.data,
                massa_muscular=form.massa_muscular.data,
                gordura=form.gordura.data,
                abdominal=form.abdominal.data,
                cintura=form.cintura.data,
                quadril=form.quadril.data,
                idade_metabolica=form.idade_metabolica.data,
            )
            db.session.add(skinfold)
            db.session.commit()
            flash("Bioimpedância adicionada com sucesso!", "success")
            return redirect(url_for("patients.view_patient", id=patient.id))
        return render_template(
            "admin/patients/add_skinfold.html", form=form, patient=patient, last_patient_height=last_patient_height
        )


@patients_bp.route("/patients/edit/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_patient(id):
    patient = Patients.query.get_or_404(id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode editar os dados dos seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
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
                return redirect(url_for("patients.list_patients"))
            except IntegrityError as e:
                db.session.rollback()
                error_message = str(e)
                if "patients.name" in str(e):
                    error_message = "Erro: Já existe um paciente com esse nome cadastrado!"
                elif "patients.cpf" in str(e):
                    error_message = "Erro: Já existe um paciente com esse CPF cadastrado!"

                flash(error_message, "danger")
        return render_template("admin/patients/edit_patient.html", form=form, patient=patient)


@patients_bp.route("/patients/<int:patient_id>/anthro/edit/<int:evaluation_id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
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
        return redirect(url_for("patients.view_patient", id=patient_id))
    return render_template("admin/patients/edit_anthro.html", form=form, diet_form=diet_form, evaluation=evaluation)


@patients_bp.route("/patients/<int:patient_id>/skinfolds/edit/<int:skinfold_id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_skinfold(patient_id, skinfold_id):
    skinfold = SkinFolds.query.get_or_404(skinfold_id)
    form = SkinfoldMeasurementForm(obj=skinfold)
    if form.validate_on_submit():
        form.populate_obj(skinfold)
        db.session.commit()
        flash("Dados de Bioimpedância atualizados com sucesso!", "success")
        return redirect(url_for("patients.view_patient", id=patient_id))
    return render_template("admin/patients/edit_skinfold.html", form=form, skinfold=skinfold)


@patients_bp.route("/patients/view/<int:id>", methods=["GET"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_patient(id):
    patient = Patients.query.get_or_404(id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode ver seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
        return render_template("admin/patients/view_patient.html", patient=patient)


@patients_bp.route("/patients/delete/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_patient(id):
    patient = Patients.query.get_or_404(id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode remover seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
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
            return redirect(url_for("patients.list_patients"))
        return render_template("admin/patients/delete_patient.html", patient=patient)


@patients_bp.route("/patients/<int:id>/view-custom-history?<pat_name>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def view_custom_history(id, pat_name):
    patient = Patients.query.get_or_404(id)
    if not block_access_to_patients(
        patient=patient,
        user=current_user,
        msg="Acesso negado: Você só pode visualizar o histórico dos seus próprios pacientes.",
        to_redirect="patients.list_patients",
    ):
        if len(patient.anthropometric_evaluations):
            patient_age = patient.anthropometric_evaluations[-1].idade
            initial_evaluation_date = patient.anthropometric_evaluations[0].data_avaliacao.strftime("%d/%m/%Y")
            last_imc = patient.anthropometric_evaluations[-1].imc
            height = patient.skinfolds[-1].altura
            initial_weight_evaluated = patient.skinfolds[0].peso
            last_weight_evaluated = patient.skinfolds[-1].peso
            ideal_weight = patient.anthropometric_evaluations[-1].p_ide
            max_weight = patient.anthropometric_evaluations[-1].p_max

            fat_percentual = "Ainda não houve registro do índice de gordura"
            muscle_percentual = "Ainda não houve registro do índice de massa magra"
            if len(patient.skinfolds):
                fat_percentual = f"{patient.skinfolds[-1].gordura}%"
                muscle_percentual = f"{patient.skinfolds[-1].massa_muscular}%"

            if len(patient.anthropometric_evaluations) > 1:
                final_weight_result = round(last_weight_evaluated - initial_weight_evaluated, 2)
                if final_weight_result < 0:
                    final_weight_result = f"Perda de {final_weight_result} Kg".replace("-", "")
                elif final_weight_result == 0:
                    final_weight_result = f"Manutenção do peso inicial: {initial_weight_evaluated} Kg"
                else:
                    final_weight_result = f"Ganho de {final_weight_result} Kg"
            else:
                final_weight_result = "Paciente ainda está na primeira avaliação"

            final_message = (
                (f"Muito bom! Seu peso máximo é {max_weight}kg e você está com " f"{last_weight_evaluated}kg.")
                if last_weight_evaluated < max_weight
                else (
                    f"Força! Mantenha o foco! Seu peso máximo é {max_weight}kg e você está com "
                    f"{last_weight_evaluated}kg."
                )
            )

            # Preparing data for evolution grafic
            evaluation_dates = [skinfold.data_medicao.strftime("%d/%m/%Y") for skinfold in patient.skinfolds]
            evaluation_weights = [skinfold.peso for skinfold in patient.skinfolds]

            return render_template(
                "admin/patients/view_custom_history.html",
                patient=patient,
                patient_age=patient_age,
                initial_evaluation_date=initial_evaluation_date,
                last_imc=last_imc,
                height=height,
                fat_percentual=fat_percentual,
                muscle_percentual=muscle_percentual,
                initial_weight_evaluated=initial_weight_evaluated,
                last_weight_evaluated=last_weight_evaluated,
                ideal_weight=ideal_weight,
                final_weight_result=final_weight_result,
                final_message=final_message,
                evaluation_dates=evaluation_dates,
                evaluation_weights=evaluation_weights,
            )

        return render_template("admin/patients/view_custom_history.html")
