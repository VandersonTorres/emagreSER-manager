import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Application settings, read from the environment with development defaults.

    Flask-Security is configured with registration, password recovery, password change and login tracking enabled, and
    its user-facing messages are translated to pt-BR (``SECURITY_MSG_*``, each one a ``(text, category)`` pair that
    keeps the ``%(placeholders)s`` of the default message).

    WhatsApp messages go through Twilio, whose credentials come from https://console.twilio.com/. E-mail goes through
    Gmail over SSL (port 465; use 587 for TLS): the account needs two-factor authentication and an "app password",
    which is what ``EMAGRESER_MAIL_PASSWORD`` must hold.

    ``SUPERUSER_EMAILS`` lists, separated by commas, semicolons or spaces, the e-mails allowed to download the database
    backup. It is empty by default, so nobody has access until it is set.
    """

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "your-secret-key")
    SECURITY_PASSWORD_SALT = os.getenv("FLASK_SECURITY_PASSWORD_SALT", "your-password-salt")
    SECURITY_REGISTERABLE = True
    SECURITY_RECOVERABLE = True
    SECURITY_TRACKABLE = True
    SECURITY_PASSWORD_HASH = "bcrypt"  # pragma: allowlist secret
    SECURITY_CHANGEABLE = True
    SECURITY_SEND_PASSWORD_CHANGE_EMAIL = False
    SECURITY_POST_LOGIN_VIEW = "/"
    SECURITY_POST_CHANGE_VIEW = "/"
    SECURITY_POST_LOGOUT_VIEW = "/login"
    SECURITY_MSG_LOGIN = ("Faça login para acessar esta página.", "info")
    SECURITY_MSG_UNAUTHENTICATED = ("Você precisa entrar para acessar este recurso.", "error")
    SECURITY_MSG_UNAUTHORIZED = ("Você não tem permissão para acessar este recurso.", "error")
    SECURITY_MSG_ANONYMOUS_USER_REQUIRED = ("Esta página só pode ser acessada sem estar conectado.", "error")
    SECURITY_MSG_INVALID_PASSWORD = ("Senha inválida, tente novamente", "error")
    SECURITY_MSG_USER_DOES_NOT_EXIST = ("Usuário não encontrado.", "error")
    SECURITY_MSG_DISABLED_ACCOUNT = ("Esta conta está desativada.", "error")
    SECURITY_MSG_PASSWORD_NOT_PROVIDED = ("Informe a senha.", "error")
    SECURITY_MSG_EMAIL_NOT_PROVIDED = ("Informe o e-mail.", "error")
    SECURITY_MSG_INVALID_EMAIL_ADDRESS = ("E-mail inválido.", "error")
    SECURITY_MSG_PASSWORD_INVALID_LENGTH = ("A senha deve ter pelo menos %(length)s caracteres.", "error")
    SECURITY_MSG_PASSWORD_IS_THE_SAME = ("A nova senha deve ser diferente da senha atual.", "error")
    SECURITY_MSG_PASSWORD_MISMATCH = ("A senha não confere.", "error")
    SECURITY_MSG_RETYPE_PASSWORD_MISMATCH = ("As senhas não conferem.", "error")
    SECURITY_MSG_PASSWORD_CHANGE = ("Senha alterada com sucesso.", "success")
    SECURITY_MSG_PASSWORD_RESET_REQUEST = (
        "As instruções para redefinir a senha foram enviadas para %(email)s.",
        "success",
    )
    SECURITY_MSG_PASSWORD_RESET = ("Senha redefinida com sucesso. Você já está conectado.", "success")
    SECURITY_MSG_PASSWORD_RESET_NO_LOGIN = ("Senha redefinida com sucesso. Entre com a nova senha.", "success")
    SECURITY_MSG_INVALID_RESET_PASSWORD_TOKEN = ("O link para redefinir a senha é inválido.", "error")
    SECURITY_MSG_PASSWORD_RESET_EXPIRED = (
        "O link para redefinir a senha expirou (prazo: %(within)s). Solicite um novo link.",
        "error",
    )
    SECURITY_MSG_REAUTHENTICATION_REQUIRED = ("Confirme sua identidade para acessar esta página.", "warning")
    SECURITY_MSG_REAUTHENTICATION_SUCCESSFUL = ("Identidade confirmada com sucesso.", "success")
    SECURITY_MSG_GENERIC_AUTHN_FAILED = ("Falha na autenticação: e-mail ou senha inválidos.", "error")

    SUPERUSER_EMAILS = os.getenv("SUPERUSER_EMAILS", "")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI", f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ALLOWED_EXTENSIONS = {"pdf"}
    TEMP_UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads/temp_files")
    os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "missing-cloud-name")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "missing-api-key")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "missing-api-secret")

    TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "Missing TWILIO SID")
    TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN", "Missing TWILIO AUTH")
    TWILIO_PHONE = os.getenv("TWILIO_PHONE", "Missing TWILIO NUMBER")

    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.getenv("EMAGRESER_MAIL_USERNAME", "emagreser.auriculo@gmail.com")
    MAIL_PASSWORD = os.getenv("EMAGRESER_MAIL_PASSWORD", "Missing Gmail Password")
    MAIL_DEFAULT_SENDER = ("EmagreSER", "emagreser.auriculo@gmail.com")
