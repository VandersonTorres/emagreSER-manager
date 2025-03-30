import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_security import current_user, roles_accepted
from flask_security.utils import hash_password

from app.models import Role, User, db

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/create_user", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def create_user():
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role_name = request.form.get("role")  # admin, nutritionist, secretary

        if not email or not password or not role_name:
            return jsonify({"error": "Email, Senha e Função são obrigatórios!"}), 400
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Usuário já está cadastrado!"}), 400

        user = User(
            username=name, email=email, active=True, password=hash_password(password), fs_uniquifier=uuid.uuid4().hex
        )
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db.session.add(role)
            db.session.commit()
        user.roles.append(role)

        db.session.add(user)
        db.session.commit()
        flash(f"Usuário {email} cadastrado com sucesso com a função {role_name}.", "success")
        return render_template("/home.html")
    return render_template("/create_user.html")


@admin_bp.route("/users")
@roles_accepted("admin", "secretary", "nutritionist")
def list_users():
    if "nutritionist" in [role.name for role in current_user.roles]:
        flash("Acesso negado! Você não tem permissão para acessar essa seção.", "danger")
        return redirect(url_for("main.index"))

    users = User.query.all()
    return render_template("list_users.html", users=users)


@admin_bp.route("/users/delete/<int:id>", methods=["GET", "POST"])
@roles_accepted("admin", "secretary", "nutritionist")
def delete_user(id):
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
