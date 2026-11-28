from flask import Blueprint, render_template
from flask_security import current_user, login_required

from app.dashboard import has_staff_role, sees_all_schedules, upcoming_schedules

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index() -> str:
    """Render the home dashboard with shortcuts and the next pending appointments.

    Accounts without a staff role get the page without the appointments card.

    :return: The rendered home page.
    """
    if not has_staff_role(current_user):
        return render_template("home.html")
    return render_template(
        "home.html",
        upcoming_schedules=upcoming_schedules(current_user),
        show_specialist=sees_all_schedules(current_user),
    )
