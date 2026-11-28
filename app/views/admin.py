"""User administration pages: create, list and remove the accounts that sign in to the system."""

import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_security import current_user, roles_accepted
from flask_security.utils import hash_password

from app.forms import USER_ROLE_LABELS, UserForm
from app.models import Role, User, db

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/create_user", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def create_user() -> ResponseReturnValue:
    """Show the form to create an account and, on a valid submission, save the user with the chosen role.

    Nutritionists are sent back to the home page. The role is created when it does not exist yet. A form with errors
    is shown again with the typed name, e-mail and role, but never the password.

    :return: The form page, or a redirect to the users list after saving.
    """
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    form = UserForm()
    if form.validate_on_submit():
        user = User(
            username=form.name.data,
            email=form.email.data,
            active=True,
            password=hash_password(form.password.data),
            fs_uniquifier=uuid.uuid4().hex,
        )
        role = Role.query.filter_by(name=form.role.data).first()
        if not role:
            role = Role(name=form.role.data)
            db.session.add(role)
            db.session.commit()
        user.roles.append(role)

        db.session.add(user)
        db.session.commit()
        flash(f"Usuário {user.email} cadastrado com sucesso com a função {USER_ROLE_LABELS[role.name]}.", "success")
        return redirect(url_for("admin.list_users"))
    return render_template("create_user.html", form=form)


@admin_bp.route("/users")
@roles_accepted("admin", "secretary", "nutritionist")
def list_users() -> ResponseReturnValue:
    """Render the list of users; nutritionists are sent back to the home page.

    :return: The rendered users page, or a redirect to the home page.
    """
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    users = User.query.all()
    return render_template("list_users.html", users=users)


@admin_bp.route("/users/delete/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_user(id: int) -> ResponseReturnValue:
    """Ask for confirmation and, on POST, delete the user; nutritionists are sent back to the home page.

    :param id: Id of the user.
    :raises NotFound: If the user does not exist.
    :return: The confirmation page, or a redirect to the users list after deleting.
    """
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    user = User.query.get_or_404(id)
    if request.method == "POST":
        db.session.delete(user)
        db.session.commit()
        flash(f"Usuário '{user.email}' removido com sucesso!", "success")
        return redirect(url_for("admin.list_users"))
    return render_template("delete_user.html", user=user)
