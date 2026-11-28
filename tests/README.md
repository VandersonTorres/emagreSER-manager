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
.venv/bin/python -m pytest -m pg_migration  # applies the migrations to PostgreSQL (needs a server, see "Migration tests")
```

The GitHub Actions workflow `.github/workflows/tests.yml` runs the first two commands on pull requests to `develop`,
`release/**` and `main`. The `pg_restore` and `pg_migration` tests run only on your machine.

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
editor (`?legacy=1`) keeping `legacy.css` without Bootstrap, which is pinned by its SHA-256 (the old `style.css` is
gone). No page renders inside a compatibility wrapper any more. Tests that need extra schedules create them in the
temporary database and delete them afterwards.

`e2e/test_responsive_layout.py` drives the shell in a browser: no horizontal overflow on the login, home and change
password pages, the mobile drawer (390x844, touch), the always visible desktop sidebar (1366x900), toast behavior and a
walk through every page of the app on both viewports. Set `SCREENSHOT_DIR` to also save one PNG per page and viewport
for visual review; without it nothing is written:

```bash
SCREENSHOT_DIR=/tmp/ui-screens .venv/bin/python -m pytest -m e2e tests/e2e/test_responsive_layout.py
```

## Diet, agenda, professional and user page tests

The diet list, the diet forms, the agenda, the booking form, the professionals and the users pages use the same layout
as the patient pages. `test_diet_list_pages.py` covers, without a browser, the cards of `#diet-list`, the drag handle,
the "PDF editado" badge, the disabled send button and its hint, the grouped actions, the single send dialog (and the
nutritionist filter of its patient select), the pinned Sortable script, the search that hides the handles, the empty
states, the new diet, edit and removal pages. `test_agenda_pages.py` covers the agenda (status badges, the weekday, the
time exactly as stored, the cancel dialogs, the filter, the empty states, the "Hoje" and "Amanhã" links with the clock
frozen at 22:30 in São Paulo) and the booking form: a missing or unknown patient, a missing professional and a bad time
flash a message and store nothing, and the conflict message and suggestions are pinned. `test_staff_pages.py` covers the
professionals and users pages and the validation of the new user form (each error, the values kept, the password never
sent back, duplicate e-mail and name, a role outside the three choices, the stored user). Tests that create rows remove
them through the ORM, so the role links go too.

`e2e/test_staff_pages.py` drives them in Chrome on both viewports: the diet reorder by dragging the handle (mouse on the
desktop, real touch events at 390x844), by keyboard and the announced result, a swipe outside the handle that scrolls
without reordering, the search that hides the handles, the send dialog (the search of the select2 inside the modal, the
mocked WhatsApp and e-mail senders and a double tap that sends once), the cancel and removal dialogs, the booking form,
the professional and user forms with their server errors, and, for every redesigned page, no sideways scroll and no page
error. The senders are replaced inside the live server process and are slow on purpose, so a second tap can reach the page.

## Patient page tests

The patient pages were redesigned without changing what their forms send, what the calculation script computes or who
can do what. `patient_cases.py` holds the records and input sets (a complete patient, a fixed evaluation and
measurement, eight evaluation cases from child to elderly and from low to high BMI, blood pressure and weight inputs),
and `patient_baselines.py` holds what the pages before the redesign sent, computed and stored for those inputs. It was
recorded in Chrome from the previous pages and is only data: do not edit it by hand. The intended differences from
the recorded pages are the "Azia / Refluxo" question, which the clinic no longer asks, and the optional "Observações"
of the bioimpedance forms, which the recording did not have. `REMOVED_FIELDS` in `patient_cases.py` lists the first, the
tests take it out of the recorded names and values, and `REMOVED_FIELD_STORED_VALUES` holds the empty answer a new
patient gets; the column stays, so the answers already stored are kept (the edit page does not touch them).
`ADDED_FIELDS` lists, by page, the fields the tests add to the recorded names, and `ADDED_FIELD_RENDERED_VALUES` holds
what the page renders in them when the stored row has nothing there. The baselines themselves are never re-recorded.

`test_patient_forms.py` (no browser) checks, for every form page, the submitted field names and the rendered values
against the baseline (the CSRF token, which every POST form carries, is checked apart), the round trip of the edit
page (open, change one field, save: only that column changes), the creation of a patient with every field and the
values stored by the evaluation and measurement forms. `form_helpers.py` reads what a browser would submit from the HTML. `test_patient_pages.py` covers
the markup: the list (data, "⋯" menu, contact links, `Remover` hidden from nutritionists), the search and its empty
states, the record (header, accessible tabs and hash keys, 14 and 11 column tables, delete forms with confirmation,
pinned Chart.js with its integrity hash), the custom history, the delete confirmation, labels, input types, back links,
and that templates and scripts carry no comments.

`test_bioimpedance_notes.py` covers the observation of a bioimpedance measurement (`note_helpers.py` adds measurements
with or without a note). The record opens a dialog with the note of the latest measurement only: the highest date, and
the highest id on a tie; no dialog when that measurement has no note, even if an older one has, and none without
measurements. The text is escaped and keeps its line breaks, every role that opens the record sees it, and the
Bioimpedância tab lists every note in a detail row under its measurement (the table keeps its 11 columns, and the row
carries the class that the "show more" button hides together with the measurement). The custom history never shows a
note. `test_patient_forms.py` covers what the forms store: NULL for a blank note, the stripped text otherwise, NULL
again after clearing it, the limit of 1000 characters and its message in Portuguese.

`test_custom_history.py` covers the custom history page. `history_cases.py` holds six patients with evaluations and
measurements (one evaluation, gain, loss, unchanged weight, fat and muscle filled and empty, measurements entered out of
order, weight equal to the maximum) and a reader of what the page shows; `history_baselines.py` holds what the page
showed for them before patients without bioimpedance were supported, read with the same reader, so the values and
texts of a complete patient must stay identical. The same file tests a patient with evaluations and no bioimpedance
(the page answers 200, shows what comes from the evaluations and the notice "Ainda não há bioimpedância registrada.",
with no chart and no Chart.js script), a patient without evaluations (page header with the name, the way back to the
record and an empty state that opens a new evaluation) and the access rules by role.

`test_clinic_dates.py` freezes the clock of `app/dates.py` to prove that `started_at`, `data_avaliacao` and
`data_medicao` take their default when the row is inserted (not when the app starts), that the two dates use the day of
São Paulo, and that the record shows "Paciente desde" in the São Paulo time zone for naive UTC and aware values.

`test_form_messages.py` checks the validation messages in Brazilian Portuguese. The translations live in
`app/forms.py` and the base form `AppForm` gives them to every form. The test reads `wtforms/locale/wtforms.pot` of the
installed WTForms and fails when a message has no translation, so an upgrade that adds messages cannot show English. It
also checks real errors (required, float, integer, date, choice) on the patient forms and on rendered pages, and that
the CSRF token is still required and accepted by the forms that validate: a request without it is refused by the
handler of `app/errors.py`, which sends the user back to the page with the Portuguese message in a toast.

`e2e/test_bioimpedance_notes.py` drives the dialog and the notes in Chrome on both viewports: the dialog is visible
after the load with the focus inside, "Entendi" and Escape close it and the focus returns to the patient name, a reload
shows it again, a long note with an unbreakable word wraps and scrolls inside it on a 390px phone, a script in a note is
text, the tab shows the notes next to their measurements and the "show more" button hides them together, and a note is
saved and cleared through the forms. It also checks the 11 and 14 columns of the two tables.

`e2e/test_patient_pages.py` replays the calculation cases in Chrome (every computed field, the age, the blood pressure
and weight normalization, and the stored rows), opens every patient page on both viewports looking for script errors and
sideways scroll, and covers the phone list, the pagination with more than one page of temporary patients, the search,
the shortcuts, the new patient form, the edit page, the record tabs with the URL hash, tables turning into cards, the
weight charts and the delete confirmations. `case_patients` and `complete_patient` (in `conftest.py`) create temporary
rows and remove them afterwards.

## CSRF protection tests

The whole app is protected by `CSRFProtect` (`app/extensions.py`, started before Flask-Security) and the token never
expires by itself (`WTF_CSRF_TIME_LIMIT = None`). The suite runs with the check off, as the other tests expect; the
`csrf_on` fixture of `test_csrf_rendering.py` turns it on for one test, in the unit tests and in the browser tests (the
live server serves the same app object).

`test_csrf_protection.py` has the route inventory, `POST_ROUTES`: one row for every endpoint that accepts a state
changing method, with the page or script that sends it, the files that hold the sender, the role that may use it and
what must stay as it was. It fails when a route is missing from the table or the table lists a route that is gone. For
each row, a POST without the token (the session already has its token, as after opening a page) must be refused (a 400
JSON answer with the sentence for scripts, a redirect with the sentence flashed for forms) and must change no row of the
affected tables, no file of the temporary folder and call no service (Cloudinary, WhatsApp, the PDF download, the backup,
mail). The `guards` fixture replaces those services and also suppresses the mail: the mail state of the session app is
built before TESTING is turned on, so it would otherwise try a real SMTP connection. The same file checks that every
page of the smoke table has the meta token and that every form with method post carries a valid token (including the
confirmation macro and the previous editor page), that representative forms do their work with the token the page
rendered (new patient, delete of an evaluation and of a measurement, patient removal, agenda, professional, users, diet
removal, e-mail and WhatsApp sends), that the reorder script and the editor save need the `X-CSRFToken` header, that an
old token is still accepted, and the handler: a same-site `Referer` is the redirect target (an https page also counts
when the request arrives over http, as behind a proxy, but an http page never counts for an https request), anything
else (another host or port, `//host`, text, nothing) goes to the home page, JSON requests get the 400 answer, and the
log line has the method, the path and the reason but never the token.

`e2e/test_csrf_flows.py` runs in Chrome with CSRF on: a save in the responsive editor (the result panel opens and the POST
carried the header), a save in the previous editor (its dialogs accepted), the diet reorder by dragging the handle, the new patient form
on the desktop and on the phone, the delete of an evaluation from the record, a form whose token input was removed (it
shows the message in a toast and changes nothing) and a post to the save endpoint with the browser cookies and no header.
It also drives `app/static/js/csrf.js` through intercepted requests: the header goes only to POST, PUT, PATCH and DELETE
requests to the page's own origin, for string, relative, `URL` and `Request` inputs and for `Headers`, array and object
headers, never over a header the caller set, never to GET, HEAD or another origin, with the body untouched.

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

## Migration tests

`test_migrations.py` reads the Alembic scripts without a database: there is exactly one head (the revision that adds
`skinfolds.observacoes`), its `down_revision` is the previous head, its source only adds and drops that nullable text
column inside `batch_alter_table`, it runs on an in-memory SQLite table, and the `Procfile` has the `release` line that
runs the migrations plus the unchanged `web` line.

`test_migration_postgres.py` applies the migration to a real PostgreSQL server the way Heroku does. The old chain of
migrations cannot build a database from nothing (its first steps alter tables the application created, and every `flask`
command creates the missing tables from the current models first), so each test builds the schema of the previous
revision from the models of commit `OLD_SCHEMA_COMMIT` (read with `git archive` into a temporary folder, never from the
working tree), runs `flask db stamp` and stores one measurement. Then it runs the exact `release:` command of the
`Procfile` (with `FLASK_SKIP_DOTENV=1` and `SQLALCHEMY_DATABASE_URI` pointing to the throwaway database) and checks the
column (type `text`, nullable, no default), the intact measurement with a NULL observation, a second release that
changes nothing, `flask db downgrade` dropping the column and a new upgrade adding it back, and that Alembic's
`compare_metadata` finds no difference on `skinfolds` between the models and the migrated database (and finds the
missing column before the migration). The tests are marked `pg_migration`, never run by default, and stop with an error
(they never skip) when `MIGRATION_TEST_DATABASE_URL` or `git` is missing. Every test creates a database with a unique
name and drops it at the end.

```bash
docker run --rm -d --name emagreser-migration-check -e POSTGRES_PASSWORD=<throwaway> -p 127.0.0.1:55433:5432 postgres:16
MIGRATION_TEST_DATABASE_URL=postgresql://postgres:<throwaway>@127.0.0.1:55433/postgres .venv/bin/python -m pytest -m pg_migration
docker rm -f emagreser-migration-check
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
