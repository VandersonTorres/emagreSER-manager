"""Deterministic synthetic PDFs, made only of vector graphics, used by the calibration tests."""

import re

import fitz

SIZES: dict[str, tuple[float, float, int]] = {
    "a4_596x842": (596, 842, 2),
    "a4_59532x84192": (595.32, 841.92, 2),
    "narrow_298x836": (298, 836, 3),
}

_MARGIN = 12
_GRID_STEP = 50
_GRID_COLOR = (0.85, 0.85, 0.85)
_BORDER_COLOR = (0.25, 0.25, 0.25)
_MARKER_FILL = (0.35, 0.35, 0.35)
_MARKER_SIZE = 10

_ID_PATTERN = re.compile(rb"/ID\[<[0-9A-Fa-f]+><[0-9A-Fa-f]+>\]")
_FIXED_ID = b"/ID[<454D414752455345522D5453542D3031><454D414752455345522D5453542D3032>]"


def make_pdf(width: float, height: float, pages: int) -> bytes:
    """Build a text-free PDF with a border, a light grid and per-page square markers.

    Page N gets N small squares in the top-left corner. The PDF has no text, so every text span found in an output PDF
    comes from the applied annotations. The random trailer /ID is replaced by a fixed one to keep the bytes stable.

    :param width: Page width in points.
    :param height: Page height in points.
    :param pages: Number of pages; the SIZES entries hold (width, height, pages).
    :return: The PDF content as bytes.
    """
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=width, height=height)

        grid = page.new_shape()
        position = _GRID_STEP
        while position < width:
            grid.draw_line((position, 0), (position, height))
            position += _GRID_STEP
        position = _GRID_STEP
        while position < height:
            grid.draw_line((0, position), (width, position))
            position += _GRID_STEP
        grid.finish(color=_GRID_COLOR, width=0.5)
        grid.commit()

        border = page.new_shape()
        border.draw_rect(fitz.Rect(_MARGIN, _MARGIN, width - _MARGIN, height - _MARGIN))
        border.finish(color=_BORDER_COLOR, width=1.5)
        border.commit()

        markers = page.new_shape()
        for marker in range(index + 1):
            left = _MARGIN + 6 + marker * (_MARKER_SIZE + 4)
            top = _MARGIN + 6
            markers.draw_rect(fitz.Rect(left, top, left + _MARKER_SIZE, top + _MARKER_SIZE))
        markers.finish(color=None, fill=_MARKER_FILL)
        markers.commit()

    doc.set_metadata({})
    data = doc.tobytes(deflate=False, garbage=0)
    doc.close()
    return _ID_PATTERN.sub(lambda match: _FIXED_ID, data)
