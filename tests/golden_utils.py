"""Helpers to record, load and diff the golden files in tests/golden."""

import difflib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def recording() -> bool:
    """Tell whether the goldens must be recorded instead of compared.

    :return: True when the GOLDEN_RECORD environment variable is "1".
    """
    return os.environ.get("GOLDEN_RECORD") == "1"


def load_golden(name: str) -> dict[str, Any]:
    """Load a golden file as parsed JSON.

    :param name: File name inside the golden directory.
    :return: The parsed JSON content.
    :raises AssertionError: If the golden file does not exist.
    """
    path = GOLDEN_DIR / name
    assert (
        path.exists()
    ), f"golden {path} does not exist; record it with GOLDEN_RECORD=1 (only if the change is approved)"
    return json.loads(path.read_text(encoding="utf-8"))


def write_golden(name: str, text: str) -> None:
    """Write a golden file, creating the golden directory when needed.

    :param name: File name inside the golden directory.
    :param text: Full file content.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / name).write_text(text, encoding="utf-8")


def dump_lines(items: Sequence[Mapping[str, Any]], indent: int) -> str:
    """Serialize a list of JSON objects with one object per line, for readable diffs.

    :param items: Objects to serialize.
    :param indent: Number of spaces the closing bracket is indented by.
    :return: The JSON array text.
    """
    if not items:
        return "[]"
    pad = " " * indent
    body = ",\n".join(pad + "  " + json.dumps(item, ensure_ascii=False) for item in items)
    return "[\n" + body + "\n" + pad + "]"


def unified_diff(expected_text: str, actual_text: str, from_label: str = "golden", to_label: str = "actual") -> str:
    """Build a unified diff between two texts.

    :param expected_text: Reference text.
    :param actual_text: Text produced by the current run.
    :param from_label: Label of the reference side.
    :param to_label: Label of the current side.
    :return: The diff text, empty when both texts are equal.
    """
    return "\n".join(
        difflib.unified_diff(
            expected_text.splitlines(),
            actual_text.splitlines(),
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
            n=2,
        )
    )
