from flask import Flask
from flask_security import Security, SQLAlchemyUserDatastore
from flask_migrate import Migrate

from config import Config
from app.models import Role, User, db
from app.views.admin import admin_bp
from app.views.main import main_bp
from app.views.schedules import schedules_bp


# Define user and role models (in models.py)
def create_app():
    app = Flask(__name__, template_folder="templates")
    app.config.from_object(Config)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Initialize extensions
    db.init_app(app)

    # Setup Flask-Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)  # noqa F841
    migrate = Migrate(app, db)  # noqa: F841

    with app.app_context():
        db.create_all()  # Create database tables if they don't exist

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")  # Admin-only routes
    app.register_blueprint(schedules_bp, url_prefix="/admin")
    return app
