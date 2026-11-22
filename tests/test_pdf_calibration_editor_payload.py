"""Golden test of the full click-to-PDF chain: recorded editor payload -> real edit_diet -> PDF spans."""

from typing import Any

import pytest
from flask import Flask

from tests.aliases import ClientFactory, SeedData
from tests.backend_helpers import apply_annotations
from tests.golden_utils import dump_lines, load_golden, recording, unified_diff, write_golden
from tests.pdf_fixtures import SIZES, make_pdf

GOLDEN_NAME = "payload_desktop_pdf.json"
PAYLOAD_GOLDEN_NAME = "payload_desktop.json"
PDF_NAME = "a4_596x842"


def _dump_golden(golden: dict[str, Any]) -> str:
    """Serialize the golden with one span per line.

    :param golden: Dict with the keys "pdf", "source" and "output".
    :return: The JSON text.
    """
    return (
        "{\n"
        f'  "pdf": "{golden["pdf"]}",\n'
        f'  "source": "{golden["source"]}",\n'
        f'  "output": {dump_lines(golden["output"], 2)}\n'
        "}\n"
    )


def test_recorded_editor_payload_produces_expected_pdf(
    app: Flask, seed: SeedData, client_for: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check where the final text lands in the PDF for the payload the editor sends on save.

    The payload comes from payload_desktop.json (the CLICKS script saved on the desktop viewport). It is POSTed to the
    real endpoint as admin over the synthetic a4_596x842 PDF, the same one the e2e serves, and the spans are compared.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    annotations = load_golden(PAYLOAD_GOLDEN_NAME)["payload"]["annotations"]
    assert annotations, "payload_desktop.json has no annotations: not a valid reference"

    spans = apply_annotations(app, seed, client_for, monkeypatch, make_pdf(*SIZES[PDF_NAME]), annotations)

    assert sorted((a["page"], a["text"]) for a in annotations) == sorted((s["page"], s["text"]) for s in spans)

    if recording():
        write_golden(
            GOLDEN_NAME,
            _dump_golden({"pdf": PDF_NAME, "source": f"{PAYLOAD_GOLDEN_NAME} (payload)", "output": spans}),
        )
        pytest.skip(f"recording {GOLDEN_NAME}")

    golden = load_golden(GOLDEN_NAME)
    assert golden["pdf"] == PDF_NAME
    assert golden["output"], "empty golden: not a valid reference"
    diff = unified_diff(
        dump_lines(golden["output"], 0), dump_lines(spans, 0), from_label=GOLDEN_NAME, to_label="actual"
    )
    assert not diff, f"The final position of the texts in the PDF changed for the editor clicks:\n{diff}"
