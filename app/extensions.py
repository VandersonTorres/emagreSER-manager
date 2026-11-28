"""Flask extensions shared by the application factory and the views."""

from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

mail = Mail()
csrf = CSRFProtect()
