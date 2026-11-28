"""Superusers: the people allowed to download the database backup, listed in ``SUPERUSER_EMAILS``."""

import re
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from flask import abort, current_app
from flask_security import current_user

P = ParamSpec("P")
R = TypeVar("R")

SEPARATORS = re.compile(r"[,;\s]+")


def superuser_emails() -> frozenset[str]:
    """Read the superuser e-mails from the application config.

    The list is parsed on every call, so a change of ``SUPERUSER_EMAILS`` applies without restarting anything.

    :return: The trimmed, lower-cased e-mails; empty when the setting is empty or missing.
    """
    raw = current_app.config.get("SUPERUSER_EMAILS") or ""
    return frozenset(email for email in SEPARATORS.split(raw.strip().lower()) if email)


def is_superuser(user: Any) -> bool:
    """Tell whether a user is a superuser, whatever the roles of the user.

    :param user: Flask-Login user, authenticated or anonymous.
    :return: ``True`` when the user is authenticated and the e-mail is in the superuser list.
    """
    if not user.is_authenticated:
        return False
    return (getattr(user, "email", None) or "").strip().lower() in superuser_emails()


def superuser_required(view: Callable[P, R]) -> Callable[P, R]:
    """Refuse the request with 403 unless the current user is a superuser.

    Meant to sit below ``login_required``, which already redirects anonymous visitors to the login page.

    :param view: The view function to protect.
    :return: The protected view.
    """

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        """Run the view for superusers and abort with 403 for everybody else.

        :param args: Positional arguments of the view.
        :param kwargs: Keyword arguments of the view.
        :raises Forbidden: If the current user is not a superuser.
        :return: The result of the view.
        """
        if not is_superuser(current_user):
            abort(403)
        return view(*args, **kwargs)

    return wrapper
