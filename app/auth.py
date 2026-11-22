"""Authentication hooks installed on Flask-Security."""

from flask import Flask, redirect, request
from flask.typing import ResponseReturnValue
from flask_security import Security, url_for_security
from flask_security.decorators import default_unauthn_handler


def wants_json() -> bool:
    """Tell whether the current request expects a JSON answer.

    :return: True for JSON requests and for clients that prefer JSON.
    """
    return request.is_json or request.accept_mimetypes.best == "application/json"


def redirect_to_login(
    mechanisms: list[str] | None = None, headers: dict[str, str] | None = None
) -> ResponseReturnValue:
    """Send an unauthenticated browser to the login page without the "please log in" alert.

    The login page already tells the visitor what to do, so opening the site shows no alert. JSON and Basic-Auth
    requests keep the Flask-Security default answer (401).

    :param mechanisms: Authentication mechanisms that were tried.
    :param headers: Headers suggested by Flask-Security for the answer.
    :return: A redirect to the login page with the requested page as ``next``, or the default 401 answer.
    """
    if wants_json() or (headers and "WWW-Authenticate" in headers):
        return default_unauthn_handler(mechanisms, headers)
    return redirect(url_for_security("login", next=request.full_path.rstrip("?")))


def register_auth_hooks(app: Flask, security: Security) -> None:
    """Install the custom unauthenticated handler.

    Flask-Security copies its handler into Flask-Login only when it starts, so the Flask-Login callback used by
    ``login_required`` is replaced as well.

    :param app: Flask application.
    :param security: Flask-Security extension of the application.
    """
    security.unauthn_handler(redirect_to_login)
    app.login_manager.unauthorized_callback = redirect_to_login
