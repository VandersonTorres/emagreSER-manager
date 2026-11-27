"""Dates of the clinic: the defaults of the models, evaluated when a row is inserted, and the display of stored times.

The database keeps times as naive UTC values, while the clinic works in the São Paulo time zone.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DATE_FORMAT = "%d/%m/%Y"


def utc_now() -> datetime:
    """Return the current UTC time without time zone information, the way the database stores it.

    :return: The current naive UTC time.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clinic_today() -> date:
    """Return the current date in the São Paulo time zone.

    :return: Today's date for the clinic.
    """
    return datetime.now(CLINIC_TIMEZONE).date()


def to_clinic_time(value: datetime) -> datetime:
    """Convert a time to the São Paulo time zone; a value without time zone is taken as UTC.

    :param value: Naive UTC time, or a time that carries its own time zone.
    :return: The same instant in the São Paulo time zone.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CLINIC_TIMEZONE)


def format_clinic_date(value: datetime | None, fmt: str = DATE_FORMAT) -> str:
    """Format the São Paulo date of a stored time, as a template filter.

    :param value: Naive UTC time, a time with its own time zone, or None.
    :param fmt: ``strftime`` format of the result.
    :return: The formatted date, or an empty string when there is no value.
    """
    if value is None:
        return ""
    return to_clinic_time(value).strftime(fmt)
