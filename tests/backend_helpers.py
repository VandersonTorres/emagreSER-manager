"""Helpers that POST annotations to the real edit_diet endpoint and read back the text spans of the generated PDF."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import fitz
import pytest
from flask import Flask, url_for

from tests.aliases import ClientFactory, SeedData


class FakeResponse:
    """Minimal stand-in for the requests response used to download the diet PDF."""

    status_code: int = 200
    text: str = ""

    def __init__(self, content: bytes) -> None:
        """Store the body of the fake response.

        :param content: PDF bytes returned as the response body.
        """
        self.content = content


def _round_values(values: Iterable[float]) -> list[float]:
    """Round numbers to 4 decimals, turning -0.0 into 0.0.

    :param values: Numbers to round.
    :return: The rounded numbers as a list.
    """
    return [round(value, 4) + 0.0 for value in values]


def extract_spans(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Read every text span of a PDF, without clipping to the page, so text that left the sheet is also seen.

    :param pdf_path: Path of the PDF file.
    :return: Spans (page, text, origin, bbox, size, font, color) sorted by page, vertical and horizontal position.
    """
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    unclipped = fitz.Rect(-10000, -10000, 10000, 10000)
    spans = []
    with fitz.open(pdf_path) as doc:
        for number, page in enumerate(doc, start=1):
            for block in page.get_text("dict", flags=flags, clip=unclipped)["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        spans.append(
                            {
                                "page": number,
                                "text": span["text"],
                                "origin": _round_values(span["origin"]),
                                "bbox": _round_values(span["bbox"]),
                                "size": round(span["size"], 4),
                                "font": span["font"],
                                "color": f"#{span['color']:06x}",
                            }
                        )
    spans.sort(key=lambda s: (s["page"], s["origin"][1], s["origin"][0], s["text"]))
    return spans


def apply_annotations(
    app: Flask,
    seed: SeedData,
    client_for: ClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    pdf: bytes,
    annotations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """POST annotations to the real edit_diet endpoint as admin and return the spans of the generated PDF.

    The endpoint runs for the "diet_backend" diet with requests.get replaced by a synthetic text-free PDF, so every
    span of the output PDF comes from the annotations. The output PDF is read from TEMP_UPLOAD_FOLDER.

    :param app: Flask application.
    :param seed: Ids of the fake records.
    :param client_for: Factory of test clients by role.
    :param monkeypatch: pytest monkeypatch fixture.
    :param pdf: Bytes of the synthetic PDF returned instead of the real download.
    :param annotations: Annotation payload items sent to the endpoint.
    :return: The text spans of the generated PDF.
    :raises AssertionError: If the endpoint does not answer with success or downloads an unexpected URL.
    """
    calls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> FakeResponse:
        """Record the requested URL and return the synthetic PDF instead of downloading.

        :param url: Requested URL.
        :param args: Ignored positional arguments.
        :param kwargs: Ignored keyword arguments.
        :return: A fake response carrying the synthetic PDF.
        """
        calls.append(url)
        return FakeResponse(pdf)

    monkeypatch.setattr("app.views.diets.requests.get", fake_get)

    with app.test_request_context():
        url = url_for("diets.edit_diet", id=seed["diet_backend"])
    response = client_for("admin").post(url, json={"annotations": annotations})

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["status"] == "success"
    assert calls == ["https://fixtures.test/diet-backend.pdf"]

    from app.models import Diet, db

    with app.app_context():
        diet = db.session.get(Diet, seed["diet_backend"])
        assert diet.temp_diet_file == f"dieta_personalizada_id_{seed['diet_backend']}.pdf"
        path = os.path.join(app.config["TEMP_UPLOAD_FOLDER"], diet.temp_diet_file)
    return extract_spans(path)
