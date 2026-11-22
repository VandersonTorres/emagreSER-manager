"""Type aliases shared by the fixtures and the tests."""

from collections.abc import Callable
from typing import TypeAlias

from flask.testing import FlaskClient

SeedData: TypeAlias = dict[str, int | str]
ClientFactory: TypeAlias = Callable[[str], FlaskClient]
