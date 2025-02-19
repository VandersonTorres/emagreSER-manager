import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Flask Settings
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

    # SQL Settings
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads Settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    ALLOWED_EXTENSIONS = {"pdf"}

    # WhatsApp API Settings
    TWILIO_SID = os.getenv("EMAGRESER_TWILIO_SID", "Missing TWILIO SID")
    TWILIO_AUTH = os.getenv("EMAGRESER_TWILIO_AUTH", "Missing TWILIO AUTH")
    TWILIO_PHONE = os.getenv("EMAGRESER_TWILIO_NUMBER", "Missing TWILIO NUMBER")

    # TODO: Mail Validation Settings
    # MAIL_SERVER = "smtp.office365.com"
    # MAIL_PORT = 587  # 465 for SSL, 587 for TLS
    # MAIL_USE_TLS = True
    # MAIL_USE_SSL = False
    # MAIL_USERNAME = os.getenv("EMAGRESER_MAIL_ADDRESS", "sirlene.torres35@hotmail.com")
    # MAIL_PASSWORD = os.getenv("EMAGRESER_MAIL_PASSWORD")
    # MAIL_DEFAULT_SENDER = "sirlene.torres35@hotmail.com"
    # SECURITY_EMAIL_SENDER = os.getenv("EMAGRESER_MAIL_ADDRESS", "sirlene.torres35@hotmail.com")
    # SECURITY_SEND_REGISTER_EMAIL = True
    # SECURITY_CONFIRMABLE = True
