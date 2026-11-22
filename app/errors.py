"""Custom pages for the 403, 404 and 500 errors; the status codes are never changed."""

from flask import Flask, current_app, render_template
from werkzeug.exceptions import HTTPException


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


def register_error_handlers(app: Flask) -> None:
    """Register the custom error pages.

    :param app: Flask application.
    """
    app.register_error_handler(403, handle_forbidden)
    app.register_error_handler(404, handle_not_found)
    app.register_error_handler(500, handle_server_error)
