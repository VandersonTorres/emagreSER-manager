"""Role-aware navigation of the application shell.

Every sidebar entry is declared once in ``NAV_ITEMS``. Adding an entry with its own visibility rule is a single new
``NavItem`` there: ``roles`` limits it to some roles, ``superuser_only`` limits it to the e-mails listed in
``SUPERUSER_EMAILS`` and ``active_on`` tells which endpoints highlight it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

from flask import Flask, request, url_for
from flask_security import current_user

from app.superusers import is_superuser


@dataclass(frozen=True)
class NavItem:
    """Declaration of one navigation entry.

    :param label: Text shown to the user (pt-BR).
    :param endpoint: Flask endpoint the entry links to.
    :param icon: Bootstrap Icons class name, without the ``bi-`` prefix.
    :param active_on: Endpoint patterns that highlight the entry; ``*`` matches any suffix (``patients.*``) and an
        exact endpoint always wins over a wildcard.
    :param roles: Role names allowed to see the entry; ``None`` shows it to every authenticated user.
    :param superuser_only: Whether only superusers see the entry, whatever their roles; it adds to ``roles``.
    """

    label: str
    endpoint: str
    icon: str
    active_on: tuple[str, ...]
    roles: frozenset[str] | None = None
    superuser_only: bool = False


@dataclass(frozen=True)
class NavLink:
    """Entry ready to be rendered by the templates.

    :param label: Text shown to the user (pt-BR).
    :param url: Target URL of the link.
    :param icon: Bootstrap Icons class name, without the ``bi-`` prefix.
    :param active: Whether the entry matches the current endpoint.
    """

    label: str
    url: str
    icon: str
    active: bool


MANAGEMENT_ROLES = frozenset({"admin", "secretary"})

NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Início", "main.index", "house-door", ("main.index",)),
    NavItem("Pacientes", "patients.list_patients", "people", ("patients.*",)),
    NavItem("Agenda", "schedules.list_schedules", "calendar3", ("schedules.*",)),
    NavItem("Agendar consulta", "schedules.schedule_action", "calendar-plus", ("schedules.schedule_action",)),
    NavItem("Dietas", "diets.list_diets", "journal-text", ("diets.*",)),
    NavItem(
        "Profissionais", "specialists.list_specialists", "person-badge", ("specialists.*",), roles=MANAGEMENT_ROLES
    ),
    NavItem("Usuários", "admin.list_users", "person-gear", ("admin.*",), roles=MANAGEMENT_ROLES),
    NavItem("Backup", "backup.show_backup", "database-down", ("backup.*",), superuser_only=True),
)


def _match_score(item: NavItem, endpoint: str | None) -> int:
    """Rate how well an entry matches an endpoint.

    :param item: Navigation entry to test.
    :param endpoint: Current endpoint, or ``None`` when no route matched.
    :return: 2 for an exact match, 1 for a wildcard match and 0 for no match.
    """
    if endpoint is None:
        return 0
    if endpoint in item.active_on:
        return 2
    if any("*" in pattern and fnmatchcase(endpoint, pattern) for pattern in item.active_on):
        return 1
    return 0


def active_item(items: Iterable[NavItem], endpoint: str | None) -> NavItem | None:
    """Pick the entry that must be highlighted for an endpoint.

    :param items: Entries to choose from.
    :param endpoint: Current endpoint, or ``None`` when no route matched.
    :return: The best matching entry, or ``None`` when nothing matches.
    """
    best: NavItem | None = None
    best_score = 0
    for item in items:
        score = _match_score(item, endpoint)
        if score > best_score:
            best, best_score = item, score
    return best


def visible_items(
    role_names: Iterable[str], items: Iterable[NavItem] = NAV_ITEMS, superuser: bool = False
) -> list[NavItem]:
    """Filter the entries a user may see.

    :param role_names: Names of the roles of the user.
    :param items: Entries to filter.
    :param superuser: Whether the user is a superuser, which unlocks the ``superuser_only`` entries.
    :return: The visible entries, in declaration order.
    """
    roles = set(role_names)
    return [
        item for item in items if (item.roles is None or item.roles & roles) and (superuser or not item.superuser_only)
    ]


def build_navigation(role_names: Iterable[str], endpoint: str | None, superuser: bool = False) -> list[NavLink]:
    """Build the sidebar links of a user for the current endpoint.

    Must run inside a request context because the URLs are resolved with ``url_for``.

    :param role_names: Names of the roles of the user.
    :param endpoint: Current endpoint, or ``None`` when no route matched.
    :param superuser: Whether the user is a superuser.
    :return: The links to render, with the active one flagged.
    """
    items = visible_items(role_names, superuser=superuser)
    current = active_item(items, endpoint)
    return [NavLink(item.label, url_for(item.endpoint), item.icon, item is current) for item in items]


def inject_navigation() -> dict[str, list[NavLink]]:
    """Provide ``nav_links`` to the templates of authenticated users.

    :return: A mapping with the sidebar links, empty for anonymous visitors.
    """
    if not current_user.is_authenticated:
        return {"nav_links": []}
    return {
        "nav_links": build_navigation(
            (role.name for role in current_user.roles), request.endpoint, superuser=is_superuser(current_user)
        )
    }


def register_navigation(app: Flask) -> None:
    """Register the navigation context processor.

    :param app: Flask application.
    """
    app.context_processor(inject_navigation)
