import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "your-secret-key")
    SECURITY_PASSWORD_SALT = os.getenv("FLASK_SECURITY_PASSWORD_SALT", "your-password-salt")
    SECURITY_REGISTERABLE = True
    SECURITY_RECOVERABLE = True
    SECURITY_TRACKABLE = True
    SECURITY_PASSWORD_HASH = "bcrypt"  # pragma: allowlist secret
    SECURITY_CHANGEABLE = True  # Enable password change functionality
    SECURITY_SEND_PASSWORD_CHANGE_EMAIL = False
    SECURITY_POST_LOGIN_VIEW = "/"
    SECURITY_POST_CHANGE_VIEW = "/profile"
    SECURITY_POST_LOGOUT_VIEW = "/login"
    SECURITY_MSG_INVALID_PASSWORD = ("Senha inválida, tente novamente", "error")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    ALLOWED_EXTENSIONS = {"pdf"}
    TWILIO_SID = "SID"
    TWILIO_AUTH = "AUTH"
    TWILIO_PHONE = "NUMBER"
