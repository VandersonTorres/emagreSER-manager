"""Writing of the diet editor annotations into PDF documents."""

import logging
from typing import Any

import fitz
from flask import current_app

from scripts.utils import hex_to_rgb_normalized


def apply_annotations(doc: fitz.Document, annotations: list[dict[str, Any]], logger: logging.Logger) -> int:
    """Write the annotations sent by the diet editor into a PDF document, in place.

    x and y are positions on a reference grid of canvasWidth x canvasHeight units (the page rendered at scale 1.64 and
    truncated), scaled proportionally to the page size in points. Every text is written in Helvetica 9pt; fontSize only
    changes the vertical adjustment. Annotations with an invalid page or without a canvas size are skipped.

    :param doc: Open PDF document that receives the texts.
    :param annotations: Annotations with text, x, y, fontSize, color, page (1-based), canvasWidth and canvasHeight.
    :param logger: Logger that receives the warnings about skipped annotations.
    :return: How many annotations were written into the document.
    """
    written = 0
    for ann in annotations:
        page_number = ann.get("page", 0) - 1
        if page_number < 0 or page_number >= len(doc):
            logger.warning(f"Ignorando anotação com página inválida: {page_number}")
            continue

        page = doc.load_page(page_number)
        text = ann.get("text", "")
        desired_fontsize = 9
        font_size = max(ann.get("fontSize", 9), 9)
        color = ann.get("color", "#000000")
        rgb = hex_to_rgb_normalized(color, current_app)

        x_canvas = ann.get("x", 0)
        y_canvas = ann.get("y", 0)
        canvas_width = ann.get("canvasWidth")
        canvas_height = ann.get("canvasHeight")

        if not canvas_width or not canvas_height:
            logger.warning("Dimensões do canvas ausentes ou inválidas.")
            continue

        page_width = page.rect.width
        page_height = page.rect.height

        x_ratio = x_canvas / canvas_width
        y_ratio = y_canvas / canvas_height

        x_pdf = x_ratio * page_width
        y_pdf = y_ratio * page_height

        font = fitz.Font("helv")
        ascender = font.ascender
        descender = font.descender

        percentual_position_ratio = desired_fontsize + round((desired_fontsize * 0.4))
        text_width = fitz.get_text_length(text, fontname="helv", fontsize=desired_fontsize)
        text_height = (
            ((ascender - descender) * font_size)
            if font_size <= desired_fontsize
            else ((ascender - descender) * (font_size / 2))
            if font_size <= percentual_position_ratio
            else (ascender - descender)
            if font_size <= (desired_fontsize * 2)
            else (ascender - descender) - (font_size / 4)
        )

        y_pdf_adjusted = y_pdf - text_height / 2

        x_pdf_adjusted = max(0, min(x_pdf, page_width - text_width))
        y_pdf_adjusted = max(0, min(y_pdf_adjusted, page_height - text_height))

        page.insert_text(
            (x_pdf_adjusted, (y_pdf_adjusted + ascender * desired_fontsize)),
            text,
            fontsize=desired_fontsize,
            color=rgb,
            fontname="helv",
        )
        written += 1
    return written
