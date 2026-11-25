"""Read-only data shown on the home dashboard."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload

from app.models import Patients, Schedules, Specialists, User

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
UPCOMING_LIMIT = 8
STAFF_ROLES = frozenset({"admin", "secretary", "nutritionist"})
WEEKDAY_ABBREVIATIONS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(frozen=True)
class UpcomingSchedule:
    """Appointment ready to be shown in the upcoming list.

    :param when_label: Weekday, date and time in pt-BR, for example ``qua, 25/11 · 14:30``.
    :param patient_id: Id of the patient.
    :param patient_name: Name of the patient.
    :param specialist: Name of the professional in charge.
    """

    when_label: str
    patient_id: int
    patient_name: str
    specialist: str


def local_now() -> datetime:
    """Get the current clinic time as a naive datetime, the same way schedules are stored.

    :return: The current time in America/Sao_Paulo without tzinfo.
    """
    return datetime.now(SAO_PAULO).replace(tzinfo=None)


def format_when(date_time: datetime) -> str:
    """Format a schedule time without depending on the server locale.

    :param date_time: Moment of the appointment.
    :return: Text such as ``qua, 25/11 · 14:30``.
    """
    return f"{WEEKDAY_ABBREVIATIONS[date_time.weekday()]}, {date_time:%d/%m} · {date_time:%H:%M}"


def has_staff_role(user: User) -> bool:
    """Tell whether a user has one of the roles that work with the patients.

    :param user: Authenticated user.
    :return: ``True`` for admins, secretaries and nutritionists; ``False`` for an account without any of them.
    """
    return bool(STAFF_ROLES & {role.name for role in user.roles})


def sees_all_schedules(user: User) -> bool:
    """Tell whether a user sees the appointments of every professional.

    Nutritionists only see their own, the same rule as the schedules list, and accounts without a staff role see none.

    :param user: Authenticated user.
    :return: ``True`` for admins and secretaries who are not nutritionists, ``False`` otherwise.
    """
    return has_staff_role(user) and "nutritionist" not in {role.name for role in user.roles}


def upcoming_schedules(user: User, now: datetime | None = None, limit: int = UPCOMING_LIMIT) -> list[UpcomingSchedule]:
    """Query the next pending appointments visible to a user, without changing any data.

    :param user: Authenticated user.
    :param now: Reference moment as a naive local datetime; defaults to the current clinic time.
    :param limit: Maximum number of appointments to return.
    :return: The appointments in ascending date order; always empty for an account without a staff role.
    """
    if not has_staff_role(user):
        return []
    query = (
        Schedules.query.join(Patients, Schedules.patient_id == Patients.id)
        .options(joinedload(Schedules.patient))
        .filter(Schedules.status == "pendente", Schedules.date_time >= (now or local_now()))
    )
    if not sees_all_schedules(user):
        specialist = Specialists.query.filter_by(email=user.email).first()
        if specialist is None:
            return []
        query = query.filter(Schedules.specialist == specialist.name)

    return [
        UpcomingSchedule(
            when_label=format_when(schedule.date_time),
            patient_id=schedule.patient.id,
            patient_name=schedule.patient.name,
            specialist=schedule.specialist,
        )
        for schedule in query.order_by(Schedules.date_time).limit(limit).all()
    ]
