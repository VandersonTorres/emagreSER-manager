import io
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, send_file, url_for
from flask.typing import ResponseReturnValue
from flask_security import current_user, login_required

from app.forms import BackupForm
from app.services.backup import SAO_PAULO, build_backup
from app.superusers import superuser_required

backup_bp = Blueprint("backup", __name__)

BACKUP_FAILED_MESSAGE = "Não foi possível gerar o backup. Tente novamente."
EXPIRED_FORM_MESSAGE = "Esta página ficou aberta por muito tempo. Atualize a página e tente novamente."


@backup_bp.get("/backup")
@login_required
@superuser_required
def show_backup() -> str:
    """Render the backup page, with what the archive holds and the download button.

    :return: The rendered page.
    """
    return render_template("admin/backup/backup.html", form=BackupForm())


@backup_bp.post("/backup")
@login_required
@superuser_required
def download_backup() -> ResponseReturnValue:
    """Build the backup archive on the fly and send it as a download, leaving an audit line in the log.

    A request without a valid CSRF token and a failure while building the archive both flash a message and go back to
    the backup page, so the user never sees an error page.

    :return: The ZIP download, or a redirect to the backup page.
    """
    if not BackupForm().validate_on_submit():
        flash(EXPIRED_FORM_MESSAGE, "error")
        return redirect(url_for("backup.show_backup"))
    try:
        archive = build_backup(current_user.email)
    except Exception:
        current_app.logger.exception("Database backup failed for %s", current_user.email)
        flash(BACKUP_FAILED_MESSAGE, "error")
        return redirect(url_for("backup.show_backup"))

    current_app.logger.warning(
        "Database backup downloaded by %s at %s (%d rows in %d tables)",
        current_user.email,
        datetime.now(SAO_PAULO).isoformat(timespec="seconds"),
        sum(archive.row_counts.values()),
        len(archive.row_counts),
    )
    response = send_file(
        io.BytesIO(archive.content), mimetype="application/zip", as_attachment=True, download_name=archive.filename
    )
    response.headers["Cache-Control"] = "no-store"
    return response
