from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_security import current_user, roles_accepted
from sqlalchemy.exc import IntegrityError

from app.forms import SpecialistForm
from app.models import Specialists, db

specialists_bp = Blueprint("specialists", __name__)


@specialists_bp.route("/specialists")
@roles_accepted("admin", "secretary", "nutritionist")
def list_specialists():
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    specialists = Specialists.query.all()
    return render_template("admin/specialists/list_specialists.html", specialists=specialists)


@specialists_bp.route("/specialists/add", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def add_specialist():
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("specialists.list_specialists"))

    form = SpecialistForm()

    if request.method == "POST" and form.validate_on_submit():
        try:
            specialist = Specialists(
                name=form.name.data, cpf=form.cpf.data, tel_number=form.tel_number.data, email=form.email.data
            )
            db.session.add(specialist)
            db.session.commit()
            flash("Profissional cadastrado com sucesso!", "success")
            return redirect(url_for("specialists.list_specialists"))
        except IntegrityError as e:
            db.session.rollback()
            flash(f"Erro ao cadastrar profissional. Verifique se os dados estão corretos. {e}", "danger")

    return render_template("admin/specialists/add_specialist.html", form=form)


@specialists_bp.route("/specialists/edit/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def edit_specialist(id):
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("specialists.list_specialists"))

    specialist = Specialists.query.get_or_404(id)
    form = SpecialistForm()
    if request.method == "POST" and form.validate_on_submit():
        try:
            specialist.name = form.name.data
            specialist.cpf = form.cpf.data
            specialist.tel_number = form.tel_number.data
            specialist.email = form.email.data

            db.session.commit()
            flash("Profissional editado com sucesso!", "success")
            return redirect(url_for("specialists.list_specialists"))
        except IntegrityError as e:
            db.session.rollback()
            flash(f"Erro ao editar profissional. Verifique os dados inseridos. {e}", "danger")

    form.name.data = specialist.name
    form.cpf.data = specialist.cpf
    form.tel_number.data = specialist.tel_number
    form.email.data = specialist.email

    return render_template("admin/specialists/edit_specialist.html", form=form, specialist=specialist)


@specialists_bp.route("/specialists/delete/<int:id>", methods=["POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_specialist(id):
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("specialists.list_specialists"))

    specialist = Specialists.query.get_or_404(id)
    try:
        db.session.delete(specialist)
        db.session.commit()
        flash("Profissional removido com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao remover profissional. Tente novamente mais tarde. {e}", "danger")

    return redirect(url_for("specialists.list_specialists"))
