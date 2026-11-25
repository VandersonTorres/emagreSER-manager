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
.venv/bin/python -m pytest              # backend golden + page smoke tests; does not run the e2e or pg_restore tests
.venv/bin/python -m pytest -m e2e       # browser e2e tests (needs internet: pdf.js CDN)
.venv/bin/python -m pytest -m pg_restore  # restores a backup into PostgreSQL (needs a server, see "Backup tests")
```

The GitHub Actions workflow `.github/workflows/tests.yml` runs the first two commands on pull requests to `develop`,
`release/**` and `main`. The `pg_restore` tests run only on your machine.

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

All knowledge of the editor DOM lives in a driver module in `tests/e2e/`. `classic_editor_driver.py` drives the previous
editor, served at `?legacy=1` (`app/templates/admin/diets/edit_diet_legacy.html`). `editor_driver.py` drives the
responsive editor (`app/templates/admin/diets/edit_diet.html`) and adds helpers for zoom, drag and the edit panel. To
cover a different editor DOM, add a driver exposing the same functions (`login`, `open_editor`, `canvas_metrics`,
`open_add_dialog`, `add_text`, `next_page`, `record_chips`, `save`) and reuse `CLICKS` and the golden from
`e2e/scenario.py`. A driver reports positions in reference pixels of the page content box (screen pixels times
`canvasWidth / contentWidth`), so the same golden applies at any display size.

## Responsive editor tests

`e2e/test_new_editor.py` runs the `CLICKS` script on the responsive editor: on the desktop viewport it must match
`payload_desktop.json` with the same 1px tolerance; on a 390x844 phone (device scale factor 3, touch), in a 900x900 window
and zoomed in it is compared with `scenario.compare_within_tolerance` (3, 3 and 1 reference pixels). It also covers
drag with the mouse and with real touch events, a PDF whose pages have different sizes (each annotation carries the
`canvasWidth` and `canvasHeight` of its own page), the payload shape, empty text, Escape, the panels, the unsaved changes
warning, a real save with the result panel and the PDF generated from the new payload against the one from the golden
payload (within 1pt). The `phone_page`, `window_900_page` and `mixed_sizes_page` fixtures live in that module.

`test_diet_pages.py` covers, without a browser, the editor and viewer markup, the previous editor at `?legacy=1` (its
files are frozen by hash), the empty states, the pinned pdf.js build and the unchanged JSON answer of the save.

## Page smoke test

`test_smoke_pages.py` uses no golden: the `EXPECTED` table records the HTTP status of every GET page for each role
(anonymous, admin, secretary, nutritionist). Notes about the recorded statuses:

- Anonymous visitors get 403 on routes protected by `@roles_accepted` (not a redirect to `/login`).
- The nutritionist is redirected away from the user and specialist management pages, from the patient delete page (any
  patient) and from patients unrelated to them.
- Patient 1 belongs to the nutritionist, patient 2 has a future schedule with the nutritionist and patient 3 has no
  relation to the nutritionist.
- `serve_temp_file` has no `@roles_accepted`: it is public on purpose, so Twilio can fetch the PDF.

Known bugs (500 responses) are recorded as `xfail(strict=True, raises=ExistingBug)`: only the current 500 counts as an
expected failure. Any other status (for example, a redirect) fails the test, and the fix (200) becomes a strict XPASS. In
both cases the table must be updated. No known bug is recorded at the moment.

## Application shell tests

`test_layout.py` covers the shell shared by every page: flash messages as toasts (rendered once, by category), the
role-aware sidebar and its active item, the home dashboard (upcoming schedules by role, no writes on GET, no form or
input), the auth pages, the custom 403, 404 and 500 pages, the pt-BR `SECURITY_MSG_*` messages and the previous diet
editor (`?legacy=1`) keeping `legacy.css` without Bootstrap. Tests that need extra schedules create them in the temporary database and
delete them afterwards.

`e2e/test_responsive_layout.py` drives the shell in a browser: no horizontal overflow on the login, home and change
password pages, the mobile drawer (390x844, touch), the always visible desktop sidebar (1366x900), toast behavior and a
walk through every page of the app on both viewports. Set `SCREENSHOT_DIR` to also save one PNG per page and viewport
for visual review; without it nothing is written:

```bash
SCREENSHOT_DIR=/tmp/ui-screens .venv/bin/python -m pytest -m e2e tests/e2e/test_responsive_layout.py
```

## Patient page tests

The patient pages were redesigned without changing what their forms send, what the calculation script computes or who
can do what. `patient_cases.py` holds the records and input sets (a complete patient, a fixed evaluation and
measurement, eight evaluation cases from child to elderly and from low to high BMI, blood pressure and weight inputs),
and `patient_baselines.py` holds what the pages before the redesign sent, computed and stored for those inputs. It was
recorded in Chrome from the previous pages and is only data: do not edit it by hand.

`test_patient_forms.py` (no browser) checks, for every form page, the submitted field names and the rendered values
against the baseline (with and without the CSRF token), the round trip of the edit page (open, change one field, save:
only that column changes), the creation of a patient with every field and the values stored by the evaluation and
measurement forms. `form_helpers.py` reads what a browser would submit from the HTML. `test_patient_pages.py` covers
the markup: the list (data, "⋯" menu, contact links, `Remover` hidden from nutritionists), the search and its empty
states, the record (header, accessible tabs and hash keys, 14 and 11 column tables, delete forms with confirmation,
pinned Chart.js with its integrity hash), the custom history, the delete confirmation, labels, input types, back links,
and that templates and scripts carry no comments.

`e2e/test_patient_pages.py` replays the calculation cases in Chrome (every computed field, the age, the blood pressure
and weight normalization, and the stored rows), opens every patient page on both viewports looking for script errors and
sideways scroll, and covers the phone list, the pagination with more than one page of temporary patients, the search,
the shortcuts, the new patient form, the edit page, the record tabs with the URL hash, tables turning into cards, the
weight charts and the delete confirmations. `case_patients` and `complete_patient` (in `conftest.py`) create temporary
rows and remove them afterwards.

## Backup tests

`test_backup.py` covers the database backup without PostgreSQL (the test database is SQLite): the superuser list
(`SUPERUSER_EMAILS`, empty in the session app; tests set it through the `set_superusers` fixture, which restores it),
the access rules (anonymous visitors go to the login page, everybody outside the list gets 403 on GET and POST, whatever
the role), the Backup menu entry, the ZIP members and names, the manifest counts, the Excel-friendly CSVs (BOM, `;`,
decimal comma, no secret columns, formula injection), the SQL script (transaction, quoted `"user"` and `"order"`,
sequences, tricky text), the audit log line, the flash on failure, a check that nothing is written to disk and a
50,000-row timing check. `test_csrf_rendering.py` also checks the token of the download form and that a POST without it
builds nothing.

`test_backup_restore.py` restores the generated script into a real PostgreSQL server with `psql -v ON_ERROR_STOP=1`:
into an empty database, into one whose empty tables already exist, and into a migrated one; it compares the counts with
the manifest and every row with the source (a temporary row with quotes, backslashes, newlines, semicolons, accents,
emoji, a leading `=`, NULLs and infinite numbers is added and removed by the `tricky_rows` fixture), checks that new
rows get the next id, and checks that restoring into a database that already has data fails and changes nothing. Each
test creates databases with unique names and drops them at the end. The tests are marked `pg_restore`, never run by
default, and fail (they never skip) when `BACKUP_RESTORE_DATABASE_URL` or `psql` is missing.

Run them against a throwaway PostgreSQL 16 (the version of Heroku Postgres), for example with Docker:

```bash
docker run --rm -d --name emagreser-restore-check -e POSTGRES_PASSWORD=<throwaway> -p 127.0.0.1:55432:5432 postgres:16
BACKUP_RESTORE_DATABASE_URL=postgresql://postgres:<throwaway>@127.0.0.1:55432/postgres .venv/bin/python -m pytest -m pg_restore
docker rm -f emagreser-restore-check
```

The container is bound to `127.0.0.1` only. Wait a few seconds after `docker run` until the server accepts connections.

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
