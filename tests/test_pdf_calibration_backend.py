"""Golden test of the server-side annotation math (edit_diet in app/views/diets.py)."""

import json
import math
import warnings
from collections.abc import Iterator
from typing import Any

import pytest
from flask import Flask

from tests.aliases import ClientFactory, SeedData
from tests.backend_helpers import apply_annotations
from tests.golden_utils import dump_lines, load_golden, recording, unified_diff, write_golden
from tests.pdf_fixtures import SIZES, make_pdf

GOLDEN_NAME = "backend.json"
SCALE = 1.64
FONT_SIZES = (8, 9, 10, 12, 13, 14, 16, 18, 19, 20)
LONG_TEXT = "Texto muito longo para estourar a margem direita"


def canvas_size(width: float, height: float) -> tuple[int, int]:
    """Compute the canvas size the editor uses for a PDF page.

    The canvas truncates the scaled size, so each side is floor(size * SCALE).

    :param width: Page width in points.
    :param height: Page height in points.
    :return: The canvas (width, height) in pixels.
    """
    return math.floor(width * SCALE), math.floor(height * SCALE)


def _cases_for_size(size_name: str) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    """Build the annotation scenarios for one synthetic PDF size.

    Payloads mimic app/static/js/pdf_editor.js: canvasWidth/canvasHeight are the truncated canvas size and x/y lie on
    that canvas grid. Font sizes 9..20 cover every text_height branch (8 becomes 9 through max). Pages outside
    [1, pages] are ignored by the server.

    :param size_name: Key of the PDF size in SIZES.
    :return: Dict "<size>/<scenario>" -> (size name, annotations).
    """
    width, height, pages = SIZES[size_name]
    cw, ch = canvas_size(width, height)

    def ann(text: str, x: float, y: float, size: int = 9, color: str = "#000000", page: int = 1) -> dict[str, Any]:
        """Build one annotation payload item on the canvas of this PDF size.

        :param text: Annotation text.
        :param x: Horizontal position on the canvas grid.
        :param y: Vertical position on the canvas grid.
        :param size: Font size.
        :param color: Text color (hex or rgb string).
        :param page: Page number the annotation belongs to.
        :return: The annotation dict.
        """
        return {
            "text": text,
            "x": round(x, 1),
            "y": round(y, 1),
            "fontSize": size,
            "color": color,
            "page": page,
            "canvasWidth": cw,
            "canvasHeight": ch,
        }

    cases = {
        "corners_and_center": [
            ann("Topo esq", 0, 0),
            ann("Topo dir", cw, 0),
            ann("Base esq", 0, ch),
            ann("Base dir", cw, ch),
            ann("Centro", cw / 2, ch / 2),
        ],
        "right_edge_long_text": [
            ann(LONG_TEXT, cw - 4, ch * 0.30),
            ann("Almoço: 2 ovos mexidos com tomate", cw * 0.95, ch * 0.40),
            ann("Curto", cw - 20, ch * 0.50),
        ],
        "bottom_edge": [
            ann("Rodape 9", cw * 0.10, ch - 2),
            ann("Rodape 20", cw * 0.40, ch - 2, size=20),
            ann("Rodape exato", cw * 0.10, ch - 15),
            ann("Muito embaixo 14", cw * 0.55, ch, size=14),
        ],
        "font_sizes": [
            ann(f"Tamanho {size}", cw * (0.05 + 0.04 * index), ch * (0.08 + 0.08 * index), size=size)
            for index, size in enumerate(FONT_SIZES)
        ],
        "colors": [
            ann("Preto hex", cw * 0.10, ch * 0.10, color="#000000"),
            ann("Vermelho hex", cw * 0.10, ch * 0.20, color="#ff0000"),
            ann("Azul rgb", cw * 0.10, ch * 0.30, color="rgb(0, 128, 255)"),
            ann("Preto rgb", cw * 0.10, ch * 0.40, color="rgb(0, 0, 0)"),
            ann("Verde HEX maiusculo", cw * 0.10, ch * 0.50, color="#00A310"),
        ],
        "accents_and_multiline": [
            ann("João", cw * 0.10, ch * 0.20),
            ann("Maçã", cw * 0.10, ch * 0.35),
            ann("Linha 1\nLinha 2", cw * 0.10, ch * 0.50),
        ],
    }

    per_page = []
    for page in range(1, pages + 1):
        per_page.append(ann(f"Pagina {page} a", cw * 0.20, ch * 0.20, page=page))
        per_page.append(ann(f"Pagina {page} b", cw * 0.55, ch * 0.70, size=12, page=page))
    per_page.append(ann("FORA depois da ultima", cw * 0.30, ch * 0.30, page=pages + 1))
    per_page.append(ann("FORA pagina zero", cw * 0.30, ch * 0.40, page=0))
    cases["all_pages_and_invalid_page"] = per_page

    return {f"{size_name}/{case}": (size_name, annotations) for case, annotations in cases.items()}


CASES: dict[str, tuple[str, list[dict[str, Any]]]] = {}
for _size_name in SIZES:
    CASES.update(_cases_for_size(_size_name))


def _dump_golden(golden: dict[str, dict[str, Any]]) -> str:
    """Serialize the backend golden with one annotation or span per line.

    :param golden: Dict case id -> {"input": annotations, "output": spans}.
    :return: The JSON text.
    """
    parts = []
    for key, case in golden.items():
        parts.append(
            f"  {json.dumps(key)}: {{\n"
            f'    "input": {dump_lines(case["input"], 4)},\n'
            f'    "output": {dump_lines(case["output"], 4)}\n'
            "  }"
        )
    return "{\n" + ",\n".join(parts) + "\n}\n"


@pytest.fixture(scope="module")
def results() -> Iterator[dict[str, dict[str, Any]]]:
    """Collect the result of every case and write the golden at the end when recording.

    The golden is only written when all cases ran; a partial recording run writes nothing and warns.

    :return: The dict filled by the tests, keyed by case id (yielded).
    """
    data = {}
    yield data
    if recording():
        if set(data) == set(CASES):
            write_golden(GOLDEN_NAME, _dump_golden(data))
        else:
            warnings.warn(f"GOLDEN_RECORD=1 with a partial run: {GOLDEN_NAME} was NOT re-recorded", stacklevel=1)


@pytest.mark.parametrize("case_id", list(CASES))
def test_backend_calibration_golden(
    app: Flask,
    seed: SeedData,
    client_for: ClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    results: dict[str, dict[str, Any]],
    case_id: str,
) -> None:
    """Check that the PDF generated for a case matches the golden.

    Each case POSTs to the real edit endpoint with requests.get replaced by a synthetic PDF and reads back the text
    spans of the generated PDF. They can only come from the annotations, because the input PDF has no text.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param monkeypatch: pytest monkeypatch fixture.
    :param results: Module-level collector of case results.
    :param case_id: Case key, "<size>/<scenario>".
    """
    size_name, annotations = CASES[case_id]
    spans = apply_annotations(app, seed, client_for, monkeypatch, make_pdf(*SIZES[size_name]), annotations)

    pages = SIZES[size_name][2]
    expected_count = sum(len(a["text"].split("\n")) for a in annotations if 1 <= a["page"] <= pages)
    assert len(spans) == expected_count
    assert not any(span["text"].startswith("FORA") for span in spans)

    actual = {"input": annotations, "output": spans}
    results[case_id] = actual
    if recording():
        return

    golden = load_golden(GOLDEN_NAME)
    assert case_id in golden, f"case {case_id} is missing from the golden"
    expected = golden[case_id]
    assert expected["output"], "empty golden: not a valid reference"
    diff = unified_diff(
        dump_lines(expected["output"], 0),
        dump_lines(actual["output"], 0),
        from_label=f"golden {case_id}",
        to_label="actual",
    )
    assert not diff, f"The PDF calibration changed:\n{diff}"
    assert expected["input"] == json.loads(json.dumps(actual["input"])), "the input payload of the case changed"


def test_backend_golden_has_no_stale_cases() -> None:
    """Check that the golden has no case that is no longer generated."""
    if recording():
        pytest.skip("recording")
    assert set(load_golden(GOLDEN_NAME)) == set(CASES)
