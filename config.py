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
    SECURITY_POST_CHANGE_VIEW = "/"
    SECURITY_POST_LOGOUT_VIEW = "/login"
    SECURITY_MSG_INVALID_PASSWORD = ("Senha inválida, tente novamente", "error")

    # SQL Settings
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI", f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads Settings
    ALLOWED_EXTENSIONS = {"pdf"}
    TEMP_UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads/temp_files")
    os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

    # Cloudinary Settings
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "missing-cloud-name")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "missing-api-key")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "missing-api-secret")

    # WhatsApp API Settings
    # https://console.twilio.com/
    TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "Missing TWILIO SID")
    TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN", "Missing TWILIO AUTH")
    TWILIO_PHONE = os.getenv("TWILIO_PHONE", "Missing TWILIO NUMBER")

    # Mail Settings
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465  # 465 for SSL, 587 for TLS
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    # Need to activate 2 factors auth and create an "app password"
    MAIL_USERNAME = os.getenv("EMAGRESER_MAIL_USERNAME", "emagreser.auriculo@gmail.com")
    MAIL_PASSWORD = os.getenv("EMAGRESER_MAIL_PASSWORD", "Missing Gmail Password")
    MAIL_DEFAULT_SENDER = ("EmagreSER", "emagreser.auriculo@gmail.com")
