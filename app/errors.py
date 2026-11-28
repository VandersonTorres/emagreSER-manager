"""Custom pages for the 403, 404 and 500 errors and the answer to a request refused by the CSRF check.

The status codes of the error pages are never changed.
"""

from urllib.parse import urlparse

from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from app.auth import wants_json

CSRF_EXPIRED_MESSAGE = "Esta página ficou aberta por muito tempo. Atualize a página e tente novamente."


def handle_forbidden(error: HTTPException) -> tuple[str, int]:
    """Render the access denied page.

    :param error: The raised 403 exception.
    :return: The rendered page and the 403 status code.
    """
    return render_template("errors/403.html"), 403


def handle_not_found(error: HTTPException) -> tuple[str, int]:
    """Render the page not found page.

    :param error: The raised 404 exception.
    :return: The rendered page and the 404 status code.
    """
    return render_template("errors/404.html"), 404


def handle_server_error(error: HTTPException) -> tuple[str, int]:
    """Render the internal error page without touching the database, the user or the navigation.

    The page is rendered straight from the template environment, which skips every context processor, because the
    database session may be unusable when this handler runs.

    :param error: The raised 500 exception.
    :return: The rendered page and the 500 status code.
    """
    return current_app.jinja_env.get_template("errors/500.html").render(), 500


def same_host_referrer() -> str | None:
    """Read the Referer header of the request when it points to a page of this same site.

    The host with its port must be the one of the request. The scheme must be the one of the request, or https when the
    request arrives over http, as it does behind a proxy that ends the encrypted connection. A protocol-relative URL,
    another host, another port, an http page for an https request and any text that is not an http or https URL are
    all refused.

    :return: The Referer, or None when it is missing or does not belong to this site.
    """
    referrer = request.referrer
    if not referrer or any(char.isspace() or char == "\\" or ord(char) < 32 for char in referrer):
        return None
    target = urlparse(referrer)
    own = urlparse(request.host_url)
    allowed_schemes = {"http", "https"} if own.scheme == "http" else {own.scheme}
    if target.scheme not in allowed_schemes or target.netloc != own.netloc:
        return None
    return referrer


def handle_csrf_error(error: CSRFError) -> ResponseReturnValue:
    """Answer a request refused because its CSRF token is missing, wrong or from another session.

    One warning line records the method, the path and the reason, never the token. A JSON request gets a JSON 400
    answer with the message. Any other request gets the message as a flashed alert and goes back to the page it came
    from when that page is of this site, or to the home page otherwise.

    :param error: The raised CSRF error.
    :return: The JSON answer with status 400, or a redirect.
    """
    current_app.logger.warning("CSRF validation failed: %s %s (%s)", request.method, request.path, error.description)
    if wants_json():
        return jsonify({"status": "error", "message": CSRF_EXPIRED_MESSAGE}), 400
    flash(CSRF_EXPIRED_MESSAGE, "error")
    return redirect(same_host_referrer() or url_for("main.index"))


def register_error_handlers(app: Flask) -> None:
    """Register the custom error pages and the answer to a refused CSRF check.

    :param app: Flask application.
    """
    app.register_error_handler(403, handle_forbidden)
    app.register_error_handler(404, handle_not_found)
    app.register_error_handler(500, handle_server_error)
    app.register_error_handler(CSRFError, handle_csrf_error)
