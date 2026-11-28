import cloudinary
from flask import Flask
from flask_migrate import Migrate
from flask_security import Security, SQLAlchemyUserDatastore

from app.auth import register_auth_hooks
from app.dates import format_clinic_date
from app.errors import register_error_handlers
from app.extensions import csrf, mail
from app.models import Role, User, db
from app.navigation import register_navigation
from app.views.admin import admin_bp
from app.views.backup import backup_bp
from app.views.diets import diets_bp
from app.views.main import main_bp
from app.views.patients import patients_bp
from app.views.schedules import schedules_bp
from app.views.specialists import specialists_bp
from config import Config


def create_app() -> Flask:
    """Build the Flask application with its extensions, blueprints, navigation and error pages.

    The User and Role models live in ``app/models.py``; the database tables are created when they do not exist yet.
    The ``clinic_date`` template filter shows a stored UTC time as a date in the São Paulo time zone. CSRF protection
    covers every state-changing request of the app, and it is initialized before Flask-Security, which asks for that.

    :return: The configured Flask application.
    """
    app = Flask(__name__, template_folder="templates")
    app.config.from_object(Config)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)
    register_auth_hooks(app, security)
    app.add_template_filter(format_clinic_date, "clinic_date")
    migrate = Migrate(app, db)  # noqa: F841

    with app.app_context():
        db.create_all()

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(backup_bp, url_prefix="/admin")
    app.register_blueprint(schedules_bp, url_prefix="/schedules-manager")
    app.register_blueprint(patients_bp, url_prefix="/patients-manager")
    app.register_blueprint(specialists_bp, url_prefix="/specialists-manager")
    app.register_blueprint(diets_bp, url_prefix="/diets-manager")
    register_navigation(app)
    register_error_handlers(app)
    return app
