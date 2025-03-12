import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_security import roles_required
from flask_security.utils import hash_password

from app.models import Role, User, db

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
