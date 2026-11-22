# Tests

Automated checks of the app. The main goal is to **prove that the calibration of the diet PDF editor does not change**
(server and browser) and that **every page keeps answering** for each role.

The tests use a temporary SQLite database, a temporary uploads folder (and a temporary process tempdir) and fake data
(`@test.local`). Nothing touches the real database or `uploads/`, and no real PDF is used: the PDFs are synthetic,
text-free and deterministic (`pdf_fixtures.py`; `SIZES` maps a size name to `(width, height, pages)`).

## Install

```bash
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

The e2e tests use the installed Google Chrome (`/usr/bin/google-chrome`). Without it, install the Playwright Chromium:
`.venv/bin/python -m playwright install chromium` and run with `E2E_BROWSER_CHANNEL=chromium`.

## Run

```bash
.venv/bin/python -m pytest              # backend golden + page smoke tests; does not run the e2e tests
.venv/bin/python -m pytest -m e2e       # browser e2e tests (needs internet: pdf.js CDN)
```

The GitHub Actions workflow `.github/workflows/tests.yml` runs both commands on pull requests to `develop`,
`release/**` and `main`.

## What each golden represents (`tests/golden/`)

| File | Test | Represents |
| --- | --- | --- |
| `backend.json` | `test_pdf_calibration_backend.py` | For each PDF size (596x842, 595.32x841.92, 298x836) and scenario (corners, edges, font sizes, colors, accents, several pages, invalid page), the text the server writes into the PDF: page, text, origin, bbox, size, font and color. Proves the math of `edit_diet` in `app/views/diets.py`. |
| `payload_desktop.json` | `e2e/test_editor_payload.py` | What the editor sends on save for a fixed click script (`CLICKS`) on a 1366x900 viewport: canvas metrics, exact payload (`x`, `y`, `canvasWidth`...) and on-screen position of the texts. Proves the browser side. |
| `payload_desktop_pdf.json` | `test_pdf_calibration_editor_payload.py` | The full click -> PDF chain, without a browser: the `payload` of `payload_desktop.json` is sent to the real `edit_diet` over the synthetic 596x842 PDF, and this golden holds the spans of the generated PDF (where each FINAL text lands on the sheet). If the payload format changes, `payload_desktop.json` fails on purpose; this golden remains the reference for the final position in the PDF (use `apply_annotations` from `backend_helpers.py` and compare with a tolerance). |

## Click script

`CLICKS` in `e2e/scenario.py` is the script every editor driver must run. `fx` and `fy` are fractions of the canvas
content box, and the points are spaced so that a click never lands on a text already added.

## Editor drivers

All knowledge of the editor DOM lives in a driver module in `tests/e2e/`. `classic_editor_driver.py` drives the editor in
`app/templates/admin/diets/edit_diet.html`. To cover a different editor DOM, add a driver exposing the same functions
(`login`, `open_editor`, `canvas_metrics`, `open_add_dialog`, `add_text`, `next_page`, `record_chips`, `save`) and reuse
`CLICKS` and the golden from `e2e/scenario.py`.

## Page smoke test

`test_smoke_pages.py` uses no golden: the `EXPECTED` table records the HTTP status of every GET page for each role
(anonymous, admin, secretary, nutritionist). Notes about the recorded statuses:

- Anonymous visitors get 403 on routes protected by `@roles_accepted` (not a redirect to `/login`).
- The nutritionist is redirected away from the user and specialist management pages, from the patient delete page (any
  patient) and from patients unrelated to them.
- Patient 1 belongs to the nutritionist, patient 2 has a future schedule with the nutritionist and patient 3 has no
  relation to the nutritionist.
- `serve_temp_file` has no `@roles_accepted`: it is public on purpose, so Twilio can fetch the PDF.

Known bugs (currently 500 responses) are recorded as `xfail(strict=True, raises=ExistingBug)`: only the current 500
counts as an expected failure. Any other status (for example, a redirect) fails the test, and the fix (200) becomes a
strict XPASS. In both cases the table must be updated.

## Re-recording goldens

Goldens are **only re-recorded** (`GOLDEN_RECORD=1`) when a behavior change was intended and approved:

```bash
GOLDEN_RECORD=1 .venv/bin/python -m pytest                # backend.json and payload_desktop_pdf.json
GOLDEN_RECORD=1 .venv/bin/python -m pytest -m e2e         # payload_desktop.json
```

`payload_desktop_pdf.json` is derived from `payload_desktop.json`: when the latter is re-recorded, re-record the former
right after (`GOLDEN_RECORD=1 .venv/bin/python -m pytest tests/test_pdf_calibration_editor_payload.py`) and review the
diff, which shows exactly how far each text moved in the PDF.

If a golden test fails after a code change, fix the code, not the golden.
