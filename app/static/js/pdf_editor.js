import { createCanvasRenderer, mountViewer, openPdf } from "./pdf_viewer.js";

/**
 * @typedef {Object} Grid
 * @property {number} width Reference width of a page, in reference pixels (canvasWidth of the payload).
 * @property {number} height Reference height of a page, in reference pixels (canvasHeight of the payload).
 */

/**
 * @typedef {Object} Annotation
 * @property {number} id Unique id; the creation order of the list is the order of the payload.
 * @property {number} page Page number, starting at 1.
 * @property {string} text Text written into the PDF.
 * @property {number} x Horizontal position in reference pixels, as the server expects it.
 * @property {number} y Vertical position in reference pixels, as the server expects it.
 * @property {number} size Font size of the preview, from MIN_FONT_SIZE to MAX_FONT_SIZE.
 * @property {string} color Text color as "#rrggbb".
 */

/**
 * @typedef {Object} Point
 * @property {number} x Horizontal coordinate.
 * @property {number} y Vertical coordinate.
 */

/**
 * @typedef {Object} PanelState
 * @property {"add" | "edit"} mode Whether the panel creates a text or edits an existing one.
 * @property {number} page Page the text belongs to.
 * @property {number} x Reference x of the text (add mode: the clicked point).
 * @property {number} y Reference y of the text (add mode: the clicked point).
 * @property {number} id Id of the edited annotation (edit mode), 0 in add mode.
 */

/**
 * @typedef {Object} DragState
 * @property {number} id Id of the dragged annotation.
 * @property {number} pointerId Pointer that holds the drag.
 * @property {Element} chip Element under the pointer.
 * @property {Point} startClient Pointer position when the drag began, in client pixels.
 * @property {Point} startPoint Pointer position when the drag began, in reference pixels.
 * @property {Point} startAnnotation Position of the annotation when the drag began.
 * @property {boolean} moved True once the pointer went further than DRAG_THRESHOLD_PX.
 */

/**
 * @typedef {Object} Dom
 * @property {HTMLElement} root Editor root.
 * @property {HTMLElement} toolbar Sticky toolbar.
 * @property {HTMLElement} stage Scrollable area around the page.
 * @property {HTMLElement} frame Page content box; its size is the displayed page.
 * @property {HTMLCanvasElement} canvas Canvas that shows the PDF page.
 * @property {HTMLElement} layer Reference-sized layer that holds the texts.
 * @property {HTMLElement} status Loading and error message.
 * @property {HTMLButtonElement} prev Previous page button.
 * @property {HTMLButtonElement} next Next page button.
 * @property {HTMLElement} pageInfo Page label.
 * @property {HTMLButtonElement} zoomOut Zoom out button.
 * @property {HTMLButtonElement} zoomFit Fit to width button.
 * @property {HTMLButtonElement} zoomIn Zoom in button.
 * @property {HTMLElement} zoomLevel Zoom label.
 * @property {HTMLButtonElement} save Save button.
 * @property {HTMLElement} saveLabel Text of the save button.
 * @property {HTMLElement} feedback Inline message area.
 * @property {HTMLFormElement} panel Text panel.
 * @property {HTMLElement} panelTitle Title of the text panel.
 * @property {HTMLInputElement} textInput Text field.
 * @property {HTMLInputElement} sizeInput Size field.
 * @property {HTMLInputElement} colorInput Color field.
 * @property {HTMLElement} nudge Group of the arrow buttons.
 * @property {HTMLButtonElement} remove Remove button.
 * @property {HTMLButtonElement} cancel Cancel button.
 * @property {HTMLButtonElement} submit Add or save button of the panel.
 * @property {HTMLDialogElement} result Result dialog.
 * @property {HTMLElement} resultViewer Container of the generated PDF viewer.
 * @property {HTMLButtonElement} resultContinue Continue editing button.
 * @property {HTMLAnchorElement} resultDownload Download link.
 * @property {HTMLAnchorElement} resultFinish Finish link.
 */

/**
 * Scale at which pdf.js paints the reference grid of a page; canvasWidth and canvasHeight of the payload come from it.
 * @type {number}
 */
const REF_SCALE = 1.64;

/**
 * Reference pixels added to a clicked position to reproduce the 1px canvas border of the first editor, which the
 * server calibration already includes.
 * @type {number}
 */
const REF_BORDER = 1;

/**
 * Reference pixels between a clicked point and the top-left corner of the text preview.
 * @type {number}
 */
const PREVIEW_OFFSET = 10;

/**
 * Reference pixels a nudge arrow moves a text.
 * @type {number}
 */
const NUDGE_STEP = 1;

/**
 * Smallest font size accepted by the editor.
 * @type {number}
 */
const MIN_FONT_SIZE = 9;

/**
 * Largest font size accepted by the editor.
 * @type {number}
 */
const MAX_FONT_SIZE = 20;

/**
 * Zoom levels, as multiples of the width that fits the available area.
 * @type {number[]}
 */
const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

/**
 * Index of the fit-to-width level in ZOOM_STEPS.
 * @type {number}
 */
const FIT_INDEX = 2;

/**
 * Smallest displayed width of a page, in CSS pixels.
 * @type {number}
 */
const MIN_PAGE_WIDTH = 120;

/**
 * Distance in client pixels a pointer must travel before a press on a text becomes a drag.
 * @type {number}
 */
const DRAG_THRESHOLD_PX = 4;

/**
 * Media query of the screens where the text panel is a bottom sheet.
 * @type {string}
 */
const SHEET_QUERY = "(max-width: 575.98px)";

/**
 * Space kept between the floating panel and the window edges, in CSS pixels.
 * @type {number}
 */
const PANEL_MARGIN_PX = 8;

/**
 * Space between the floating panel and the point it refers to, in CSS pixels.
 * @type {number}
 */
const PANEL_GAP_PX = 14;

/**
 * Space kept between the clicked point and the bottom sheet when the page scrolls to reveal it, in CSS pixels.
 * @type {number}
 */
const SHEET_REVEAL_GAP_PX = 24;

/**
 * Color of a new text until the user picks another one.
 * @type {string}
 */
const DEFAULT_COLOR = "#000000";

/**
 * Decimals kept in the positions sent to the server.
 * @type {number}
 */
const POSITION_DECIMALS = 3;

/**
 * Message of the inline notice when the PDF cannot be loaded.
 * @type {string}
 */
const LOAD_ERROR_MESSAGE = "Não foi possível carregar o PDF. Atualize a página ou use o editor antigo.";

/**
 * Message of the inline notice when a page cannot be loaded.
 * @type {string}
 */
const PAGE_ERROR_MESSAGE = "Não foi possível carregar esta página. Atualize a página e tente novamente.";

/**
 * Message of the inline notice when there is nothing to save.
 * @type {string}
 */
const EMPTY_SAVE_MESSAGE = "Adicione ao menos um texto antes de salvar.";

/**
 * Message of the inline notice when the save fails without a message from the server.
 * @type {string}
 */
const SAVE_ERROR_MESSAGE = "Não foi possível salvar o PDF. Tente novamente.";

/**
 * Message of the inline notice when the save request does not reach the server.
 * @type {string}
 */
const NETWORK_ERROR_MESSAGE = "Não foi possível salvar o PDF. Verifique a conexão e tente novamente.";

/**
 * Editor state.
 * @type {{
 *   doc: {numPages: number, getPage: function(number): Promise<any>} | null,
 *   pdfPage: any,
 *   page: number,
 *   pageCount: number,
 *   pageTicket: number,
 *   grids: Object<number, Grid>,
 *   displayWidth: number,
 *   availableWidth: number,
 *   zoomIndex: number,
 *   annotations: Annotation[],
 *   nextId: number,
 *   lastSize: number,
 *   lastColor: string,
 *   dirty: boolean,
 *   saving: boolean,
 *   panel: PanelState | null,
 *   drag: DragState | null,
 *   suppressClick: boolean,
 *   resultViewer: {destroy: function(): void} | null
 * }}
 */
const state = {
    doc: null,
    pdfPage: null,
    page: 1,
    pageCount: 0,
    pageTicket: 0,
    grids: {},
    displayWidth: 0,
    availableWidth: 0,
    zoomIndex: FIT_INDEX,
    annotations: [],
    nextId: 1,
    lastSize: MIN_FONT_SIZE,
    lastColor: DEFAULT_COLOR,
    dirty: false,
    saving: false,
    panel: null,
    drag: null,
    suppressClick: false,
    resultViewer: null,
};

/**
 * Elements of the editor, collected by init.
 * @type {Dom}
 */
let dom;

/**
 * Renderer of the page canvas, created by init.
 * @type {import("./pdf_viewer.js").CanvasRenderer}
 */
let renderer;

/**
 * Converts a pointer position into reference pixels of a page; the only place where screen and reference units meet.
 *
 * The content box must be measured with getBoundingClientRect when the event happens, so the result is valid at any
 * display size, browser zoom or pinch. REF_BORDER reproduces the 1px canvas border the server calibration includes.
 * @param {number} clientX Horizontal pointer position in client pixels.
 * @param {number} clientY Vertical pointer position in client pixels.
 * @param {{left: number, top: number, width: number, height: number}} content Page content box on the screen.
 * @param {Grid} grid Reference size of the page.
 * @returns {Point} The position in reference pixels.
 */
function toReference(clientX, clientY, content, grid) {
    return {
        x: ((clientX - content.left) * grid.width) / content.width + REF_BORDER,
        y: ((clientY - content.top) * grid.height) / content.height + REF_BORDER,
    };
}

/**
 * Finds an element of the editor by its id.
 * @param {string} id Element id.
 * @returns {HTMLElement} The element.
 */
function byId(id) {
    return /** @type {HTMLElement} */ (document.getElementById(id));
}

/**
 * Collects the elements of the editor.
 * @param {HTMLElement} root Editor root.
 * @returns {Dom} The elements.
 */
function collectDom(root) {
    return {
        root,
        toolbar: byId("pdfe-toolbar"),
        stage: byId("pdfe-stage"),
        frame: byId("pdfe-frame"),
        canvas: /** @type {HTMLCanvasElement} */ (byId("pdfe-canvas")),
        layer: byId("pdfe-layer"),
        status: byId("pdfe-status"),
        prev: /** @type {HTMLButtonElement} */ (byId("pdfe-prev")),
        next: /** @type {HTMLButtonElement} */ (byId("pdfe-next")),
        pageInfo: byId("pdfe-page-info"),
        zoomOut: /** @type {HTMLButtonElement} */ (byId("pdfe-zoom-out")),
        zoomFit: /** @type {HTMLButtonElement} */ (byId("pdfe-zoom-fit")),
        zoomIn: /** @type {HTMLButtonElement} */ (byId("pdfe-zoom-in")),
        zoomLevel: byId("pdfe-zoom-level"),
        save: /** @type {HTMLButtonElement} */ (byId("pdfe-save")),
        saveLabel: byId("pdfe-save-label"),
        feedback: byId("pdfe-feedback"),
        panel: /** @type {HTMLFormElement} */ (byId("pdfe-panel")),
        panelTitle: byId("pdfe-panel-title"),
        textInput: /** @type {HTMLInputElement} */ (byId("pdfe-text")),
        sizeInput: /** @type {HTMLInputElement} */ (byId("pdfe-size")),
        colorInput: /** @type {HTMLInputElement} */ (byId("pdfe-color")),
        nudge: byId("pdfe-nudge"),
        remove: /** @type {HTMLButtonElement} */ (byId("pdfe-remove")),
        cancel: /** @type {HTMLButtonElement} */ (byId("pdfe-cancel")),
        submit: /** @type {HTMLButtonElement} */ (byId("pdfe-submit")),
        result: /** @type {HTMLDialogElement} */ (byId("pdfe-result")),
        resultViewer: byId("pdfe-result-viewer"),
        resultContinue: /** @type {HTMLButtonElement} */ (byId("pdfe-result-continue")),
        resultDownload: /** @type {HTMLAnchorElement} */ (byId("pdfe-result-download")),
        resultFinish: /** @type {HTMLAnchorElement} */ (byId("pdfe-result-finish")),
    };
}

/**
 * Limits a number to a range.
 * @param {number} value Number to limit.
 * @param {number} min Lowest allowed value.
 * @param {number} max Highest allowed value.
 * @returns {number} The limited number.
 */
function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

/**
 * Rounds a position to the decimals sent to the server.
 * @param {number} value Position in reference pixels.
 * @returns {number} The rounded position.
 */
function roundPosition(value) {
    const factor = 10 ** POSITION_DECIMALS;
    return Math.round(value * factor) / factor;
}

/**
 * Collapses the white space of a text the way the preview shows it, and trims it.
 * @param {string} value Text typed by the user.
 * @returns {string} The normalized text.
 */
function normalizeText(value) {
    return value.replace(/\s+/g, " ").trim();
}

/**
 * Reads a font size, falling back to the last used one and keeping it inside the accepted range.
 * @param {string} value Text of the size field.
 * @returns {number} Font size as an integer.
 */
function normalizeSize(value) {
    const parsed = parseInt(value, 10);
    return clamp(Number.isNaN(parsed) ? state.lastSize : parsed, MIN_FONT_SIZE, MAX_FONT_SIZE);
}

/**
 * Formats a "#rrggbb" color the way browsers serialize it, as the server expects.
 * @param {string} hex Color as "#rrggbb".
 * @returns {string} The color as "rgb(r, g, b)".
 */
function toRgbString(hex) {
    const value = parseInt(hex.slice(1), 16);
    return `rgb(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255})`;
}

/**
 * Finds an annotation by id.
 * @param {number} id Annotation id.
 * @returns {Annotation | null} The annotation, or null when it does not exist.
 */
function findAnnotation(id) {
    for (const annotation of state.annotations) {
        if (annotation.id === id) {
            return annotation;
        }
    }
    return null;
}

/**
 * Finds the text element of an annotation on the current page.
 * @param {number} id Annotation id.
 * @returns {HTMLElement | null} The element, or null when the annotation is on another page.
 */
function findChip(id) {
    return /** @type {HTMLElement | null} */ (dom.layer.querySelector(`[data-id="${id}"]`));
}

/**
 * Finds the text element that contains an event target.
 * @param {EventTarget | null} target Target of the event.
 * @returns {HTMLElement | null} The text element, or null when the target is not inside one.
 */
function closestChip(target) {
    if (!(target instanceof Element)) {
        return null;
    }
    return /** @type {HTMLElement | null} */ (target.closest(".pdfe-chip"));
}

/**
 * Returns the reference size of the current page.
 * @returns {Grid} The grid of the page.
 */
function currentGrid() {
    return state.grids[state.page];
}

/**
 * Marks the editor as having changes that were not saved yet.
 * @returns {void}
 */
function markDirty() {
    state.dirty = true;
}

/**
 * Shows an inline message above the page.
 * @param {string} message Text of the message.
 * @param {"error" | "info"} kind Style of the message.
 * @returns {void}
 */
function showFeedback(message, kind) {
    dom.feedback.dataset.kind = kind;
    dom.feedback.textContent = message;
}

/**
 * Clears the inline message.
 * @returns {void}
 */
function clearFeedback() {
    dom.feedback.textContent = "";
    delete dom.feedback.dataset.kind;
}

/**
 * Updates the page label, the page buttons, the zoom label and the zoom buttons.
 * @returns {void}
 */
function updateToolbar() {
    dom.pageInfo.textContent = `Página ${state.page} de ${state.pageCount}`;
    dom.prev.disabled = state.page <= 1;
    dom.next.disabled = state.page >= state.pageCount;
    dom.zoomOut.disabled = state.zoomIndex <= 0;
    dom.zoomIn.disabled = state.zoomIndex >= ZOOM_STEPS.length - 1;
    dom.zoomFit.disabled = state.zoomIndex === FIT_INDEX;
    dom.save.disabled = state.saving;
}

/**
 * Measures the width available to the page inside the stage.
 * @returns {number} Width in CSS pixels, without the stage padding.
 */
function measureAvailableWidth() {
    const style = getComputedStyle(dom.stage);
    return dom.stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
}

/**
 * Sizes the page frame, the text layer and the zoom label for the current page and zoom level.
 *
 * The frame is as wide as the available area but never wider than the reference grid (100%); the text layer keeps the
 * reference size and is scaled to the frame, so the texts follow the page at any size.
 * @returns {void}
 */
function layoutPage() {
    const grid = currentGrid();
    state.availableWidth = measureAvailableWidth();
    const fit = Math.min(state.availableWidth, grid.width);
    const width = Math.max(MIN_PAGE_WIDTH, Math.floor(fit * ZOOM_STEPS[state.zoomIndex]));
    const height = (width * grid.height) / grid.width;
    const scale = width / grid.width;
    state.displayWidth = width;
    dom.frame.style.width = `${width}px`;
    dom.frame.style.height = `${height}px`;
    dom.frame.style.setProperty("--pdfe-scale", String(scale));
    dom.layer.style.width = `${grid.width}px`;
    dom.layer.style.height = `${grid.height}px`;
    dom.layer.style.transform = `scale(${scale})`;
    dom.frame.dataset.canvasWidth = String(grid.width);
    dom.frame.dataset.canvasHeight = String(grid.height);
    dom.zoomLevel.textContent = `${Math.round(scale * 100)}%`;
}

/**
 * Paints the current PDF page at the displayed width.
 * @returns {Promise<void>} Resolves when the page is painted or replaced by a newer painting.
 */
async function paintPage() {
    const pdfPage = state.pdfPage;
    if (!pdfPage) {
        return;
    }
    dom.frame.dataset.state = "rendering";
    let painted = false;
    try {
        painted = await renderer.render(pdfPage, state.displayWidth);
    } catch {
        dom.frame.dataset.state = "error";
        showFeedback(PAGE_ERROR_MESSAGE, "error");
        return;
    }
    if (painted) {
        dom.frame.dataset.state = "ready";
        dom.frame.dataset.page = String(state.page);
        dom.root.dataset.state = "ready";
    }
}

/**
 * Applies the content, position and style of an annotation to its text element.
 * @param {HTMLElement} chip Text element.
 * @param {Annotation} annotation Annotation to show.
 * @returns {void}
 */
function paintChip(chip, annotation) {
    chip.textContent = annotation.text;
    chip.style.left = `${annotation.x - PREVIEW_OFFSET - REF_BORDER}px`;
    chip.style.top = `${annotation.y - PREVIEW_OFFSET - REF_BORDER}px`;
    chip.style.fontSize = `${annotation.size}px`;
    chip.style.color = annotation.color;
    chip.setAttribute("aria-label", `Editar texto: ${annotation.text}`);
}

/**
 * Creates the text element of an annotation.
 * @param {Annotation} annotation Annotation to show.
 * @returns {HTMLElement} The new element.
 */
function createChip(annotation) {
    const chip = document.createElement("div");
    chip.className = "pdfe-chip";
    chip.dataset.id = String(annotation.id);
    chip.dataset.page = String(annotation.page);
    chip.tabIndex = 0;
    chip.setAttribute("role", "button");
    paintChip(chip, annotation);
    return chip;
}

/**
 * Shows only the texts of the current page.
 * @returns {void}
 */
function renderChips() {
    dom.layer.replaceChildren();
    for (const annotation of state.annotations) {
        if (annotation.page === state.page) {
            dom.layer.append(createChip(annotation));
        }
    }
}

/**
 * Tells whether the text panel is a bottom sheet on the current screen.
 * @returns {boolean} True on phones.
 */
function isSheet() {
    return window.matchMedia(SHEET_QUERY).matches;
}

/**
 * Computes how far the visual viewport is from the bottom of the layout viewport, so the sheet stays above the keyboard.
 * @returns {number} Distance in CSS pixels.
 */
function measureSheetOffset() {
    const viewport = window.visualViewport;
    if (!viewport) {
        return 0;
    }
    return Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
}

/**
 * Finds the screen rectangle the open panel refers to: the anchor marker of a new text or the edited text.
 * @returns {DOMRect | null} The rectangle in client pixels, or null when no panel is open.
 */
function panelTargetRect() {
    const panel = state.panel;
    if (!panel) {
        return null;
    }
    const target = panel.mode === "add" ? dom.layer.querySelector(".pdfe-anchor") : findChip(panel.id);
    return target ? target.getBoundingClientRect() : null;
}

/**
 * Scrolls the page so the point of the open panel is not hidden behind the bottom sheet.
 * @returns {void}
 */
function revealTarget() {
    const rect = panelTargetRect();
    if (!rect || !isSheet()) {
        return;
    }
    const viewport = window.visualViewport;
    const bottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
    const limit = bottom - dom.panel.offsetHeight - SHEET_REVEAL_GAP_PX;
    if (rect.bottom > limit) {
        window.scrollBy({ top: rect.bottom - limit, behavior: "instant" });
    }
}

/**
 * Places the open panel: near its point on large screens, at the bottom of the screen on phones.
 * @returns {void}
 */
function positionPanel() {
    const rect = panelTargetRect();
    const style = dom.panel.style;
    if (isSheet()) {
        style.left = "";
        style.top = "";
        style.setProperty("--pdfe-sheet-offset", `${measureSheetOffset()}px`);
        return;
    }
    if (!rect) {
        return;
    }
    const width = dom.panel.offsetWidth;
    const height = dom.panel.offsetHeight;
    const centerX = rect.left + rect.width / 2;
    const highest = Math.max(PANEL_MARGIN_PX, dom.toolbar.getBoundingClientRect().bottom + PANEL_MARGIN_PX);
    let top = rect.top - height - PANEL_GAP_PX;
    if (top < highest) {
        top = rect.bottom + PANEL_GAP_PX;
    }
    style.left = `${clamp(centerX - width / 2, PANEL_MARGIN_PX, window.innerWidth - width - PANEL_MARGIN_PX)}px`;
    style.top = `${clamp(top, PANEL_MARGIN_PX, window.innerHeight - height - PANEL_MARGIN_PX)}px`;
}

/**
 * Keeps the open panel in place and its point visible when the window or the visual viewport is resized.
 * @returns {void}
 */
function onViewportResize() {
    if (state.panel) {
        positionPanel();
        revealTarget();
    }
}

/**
 * Keeps the open panel in place when the visual viewport is panned.
 * @returns {void}
 */
function onViewportScroll() {
    if (state.panel) {
        positionPanel();
    }
}

/**
 * Creates the marker that shows where a new text will go.
 * @param {number} x Reference x of the clicked point.
 * @param {number} y Reference y of the clicked point.
 * @returns {void}
 */
function showAnchor(x, y) {
    removeAnchor();
    const anchor = document.createElement("div");
    anchor.className = "pdfe-anchor";
    anchor.style.left = `${x - REF_BORDER}px`;
    anchor.style.top = `${y - REF_BORDER}px`;
    dom.layer.append(anchor);
}

/**
 * Removes the marker of the point of a new text.
 * @returns {void}
 */
function removeAnchor() {
    const anchor = dom.layer.querySelector(".pdfe-anchor");
    if (anchor) {
        anchor.remove();
    }
}

/**
 * Opens the text panel in a mode, fills its fields and focuses the text field right away.
 * @param {PanelState} panel What the panel works on.
 * @param {string} text Initial text.
 * @param {number} size Initial font size.
 * @param {string} color Initial color as "#rrggbb".
 * @returns {void}
 */
function openPanel(panel, text, size, color) {
    const editing = panel.mode === "edit";
    state.panel = panel;
    dom.panel.dataset.mode = panel.mode;
    dom.panelTitle.textContent = editing ? "Editar texto" : "Adicionar texto";
    dom.submit.textContent = editing ? "Salvar" : "Adicionar";
    dom.textInput.value = text;
    dom.textInput.removeAttribute("aria-invalid");
    dom.sizeInput.value = String(size);
    dom.colorInput.value = color;
    dom.root.dataset.panel = "open";
    dom.panel.hidden = false;
    if (editing) {
        const chip = findChip(panel.id);
        if (chip) {
            chip.classList.add("pdfe-chip-active");
        }
    } else {
        showAnchor(panel.x, panel.y);
    }
    positionPanel();
    dom.textInput.focus({ preventScroll: true });
    if (editing) {
        const end = dom.textInput.value.length;
        dom.textInput.setSelectionRange(end, end);
    }
    revealTarget();
    positionPanel();
}

/**
 * Closes the text panel without applying anything.
 * @param {boolean} restoreFocus True to move the focus back to the text that was being edited.
 * @returns {void}
 */
function closePanel(restoreFocus) {
    const panel = state.panel;
    if (!panel) {
        return;
    }
    state.panel = null;
    dom.panel.hidden = true;
    delete dom.root.dataset.panel;
    removeAnchor();
    const active = dom.layer.querySelector(".pdfe-chip-active");
    if (active) {
        active.classList.remove("pdfe-chip-active");
    }
    if (restoreFocus && panel.mode === "edit") {
        const chip = findChip(panel.id);
        if (chip) {
            chip.focus({ preventScroll: true });
        }
    }
}

/**
 * Opens the panel to add a text at a clicked point; a click while an add panel is open moves its point and keeps what was typed.
 * @param {Point} point Clicked point in reference pixels.
 * @returns {void}
 */
function openAddPanel(point) {
    const panel = /** @type {PanelState} */ ({ mode: "add", page: state.page, x: point.x, y: point.y, id: 0 });
    if (state.panel && state.panel.mode === "add") {
        const text = dom.textInput.value;
        const size = normalizeSize(dom.sizeInput.value);
        const color = dom.colorInput.value;
        closePanel(false);
        openPanel(panel, text, size, color);
        return;
    }
    closePanel(false);
    openPanel(panel, "", state.lastSize, state.lastColor);
}

/**
 * Opens the panel to edit a text.
 * @param {Annotation} annotation Annotation to edit.
 * @returns {void}
 */
function openEditPanel(annotation) {
    closePanel(false);
    const panel = /** @type {PanelState} */ ({
        mode: "edit",
        page: annotation.page,
        x: annotation.x,
        y: annotation.y,
        id: annotation.id,
    });
    openPanel(panel, annotation.text, annotation.size, annotation.color);
}

/**
 * Adds an annotation to the end of the list and shows it when it belongs to the current page.
 * @param {PanelState} panel Add panel that holds the clicked point.
 * @param {string} text Normalized text.
 * @param {number} size Font size.
 * @param {string} color Color as "#rrggbb".
 * @returns {void}
 */
function addAnnotation(panel, text, size, color) {
    /** @type {Annotation} */
    const annotation = { id: state.nextId, page: panel.page, text, x: panel.x, y: panel.y, size, color };
    state.nextId += 1;
    state.annotations.push(annotation);
    state.lastSize = size;
    state.lastColor = color;
    if (panel.page === state.page) {
        dom.layer.append(createChip(annotation));
    }
    markDirty();
}

/**
 * Applies the panel fields to the edited annotation.
 * @param {Annotation} annotation Annotation being edited.
 * @param {string} text Normalized text.
 * @param {number} size Font size.
 * @param {string} color Color as "#rrggbb".
 * @returns {void}
 */
function updateAnnotation(annotation, text, size, color) {
    const changed = annotation.text !== text || annotation.size !== size || annotation.color !== color;
    annotation.text = text;
    annotation.size = size;
    annotation.color = color;
    const chip = findChip(annotation.id);
    if (chip) {
        paintChip(chip, annotation);
    }
    if (changed) {
        markDirty();
    }
}

/**
 * Adds or saves the text of the open panel.
 * @param {SubmitEvent} event Submit event of the panel form.
 * @returns {void}
 */
function onPanelSubmit(event) {
    event.preventDefault();
    const panel = state.panel;
    if (!panel) {
        return;
    }
    const text = normalizeText(dom.textInput.value);
    const size = normalizeSize(dom.sizeInput.value);
    const color = dom.colorInput.value || DEFAULT_COLOR;
    if (panel.mode === "add") {
        if (text) {
            addAnnotation(panel, text, size, color);
        }
        closePanel(false);
        return;
    }
    const annotation = findAnnotation(panel.id);
    if (!annotation) {
        closePanel(false);
        return;
    }
    if (!text) {
        dom.textInput.setAttribute("aria-invalid", "true");
        dom.textInput.focus({ preventScroll: true });
        return;
    }
    updateAnnotation(annotation, text, size, color);
    closePanel(true);
}

/**
 * Clears the invalid mark of the text field once the user types.
 * @returns {void}
 */
function onTextInput() {
    dom.textInput.removeAttribute("aria-invalid");
}

/**
 * Closes the panel without changes.
 * @returns {void}
 */
function onPanelCancel() {
    closePanel(true);
}

/**
 * Removes the text that is being edited.
 * @returns {void}
 */
function onPanelRemove() {
    const panel = state.panel;
    if (!panel || panel.mode !== "edit") {
        return;
    }
    const kept = [];
    for (const annotation of state.annotations) {
        if (annotation.id !== panel.id) {
            kept.push(annotation);
        }
    }
    state.annotations = kept;
    const chip = findChip(panel.id);
    if (chip) {
        chip.remove();
    }
    markDirty();
    closePanel(false);
}

/**
 * Moves the edited text by the step of the pressed arrow.
 * @param {MouseEvent} event Click on the arrow group.
 * @returns {void}
 */
function onNudge(event) {
    const button = event.target instanceof Element ? event.target.closest("button[data-dx]") : null;
    const panel = state.panel;
    if (!button || !panel || panel.mode !== "edit") {
        return;
    }
    const annotation = findAnnotation(panel.id);
    if (!annotation) {
        return;
    }
    const grid = currentGrid();
    const dx = Number(/** @type {HTMLElement} */ (button).dataset.dx) * NUDGE_STEP;
    const dy = Number(/** @type {HTMLElement} */ (button).dataset.dy) * NUDGE_STEP;
    annotation.x = clamp(annotation.x + dx, REF_BORDER, grid.width + REF_BORDER);
    annotation.y = clamp(annotation.y + dy, REF_BORDER, grid.height + REF_BORDER);
    const chip = findChip(annotation.id);
    if (chip) {
        paintChip(chip, annotation);
    }
    markDirty();
}

/**
 * Handles Escape while a panel is open.
 * @param {KeyboardEvent} event Key press anywhere in the page.
 * @returns {void}
 */
function onDocumentKeydown(event) {
    if (event.key === "Escape" && state.panel && !dom.result.open) {
        event.preventDefault();
        closePanel(true);
    }
}

/**
 * Opens the add panel at the clicked point, or the edit panel of a clicked text.
 * @param {MouseEvent} event Click inside the page frame.
 * @returns {void}
 */
function onFrameClick(event) {
    const chip = closestChip(event.target);
    if (chip) {
        if (state.suppressClick) {
            state.suppressClick = false;
            return;
        }
        const annotation = findAnnotation(Number(chip.dataset.id));
        if (annotation) {
            openEditPanel(annotation);
        }
        return;
    }
    const content = dom.frame.getBoundingClientRect();
    if (!state.pdfPage || content.width === 0 || content.height === 0) {
        return;
    }
    openAddPanel(toReference(event.clientX, event.clientY, content, currentGrid()));
}

/**
 * Opens the edit panel of a focused text with Enter or Space.
 * @param {KeyboardEvent} event Key press inside the page frame.
 * @returns {void}
 */
function onFrameKeydown(event) {
    const chip = closestChip(event.target);
    if (!chip || (event.key !== "Enter" && event.key !== " ")) {
        return;
    }
    event.preventDefault();
    const annotation = findAnnotation(Number(chip.dataset.id));
    if (annotation) {
        openEditPanel(annotation);
    }
}

/**
 * Starts dragging a text when a pointer presses it.
 * @param {PointerEvent} event Pointer press inside the page frame.
 * @returns {void}
 */
function onPointerDown(event) {
    const chip = closestChip(event.target);
    if (!chip || (event.pointerType === "mouse" && event.button !== 0)) {
        return;
    }
    const annotation = findAnnotation(Number(chip.dataset.id));
    const content = dom.frame.getBoundingClientRect();
    if (!annotation || content.width === 0) {
        return;
    }
    state.suppressClick = false;
    state.drag = {
        id: annotation.id,
        pointerId: event.pointerId,
        chip,
        startClient: { x: event.clientX, y: event.clientY },
        startPoint: toReference(event.clientX, event.clientY, content, currentGrid()),
        startAnnotation: { x: annotation.x, y: annotation.y },
        moved: false,
    };
    chip.setPointerCapture(event.pointerId);
}

/**
 * Moves the dragged text with the pointer, keeping the point where it was grabbed.
 * @param {PointerEvent} event Pointer move inside the page frame.
 * @returns {void}
 */
function onPointerMove(event) {
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) {
        return;
    }
    const travelled = Math.hypot(event.clientX - drag.startClient.x, event.clientY - drag.startClient.y);
    if (!drag.moved && travelled < DRAG_THRESHOLD_PX) {
        return;
    }
    const annotation = findAnnotation(drag.id);
    const content = dom.frame.getBoundingClientRect();
    if (!annotation || content.width === 0) {
        return;
    }
    drag.moved = true;
    const grid = currentGrid();
    const point = toReference(event.clientX, event.clientY, content, grid);
    annotation.x = clamp(drag.startAnnotation.x + point.x - drag.startPoint.x, REF_BORDER, grid.width + REF_BORDER);
    annotation.y = clamp(drag.startAnnotation.y + point.y - drag.startPoint.y, REF_BORDER, grid.height + REF_BORDER);
    paintChip(/** @type {HTMLElement} */ (drag.chip), annotation);
    drag.chip.classList.add("pdfe-chip-dragging");
}

/**
 * Ends the drag; a press that never moved is left to the click that follows.
 * @param {PointerEvent} event Pointer release or cancellation.
 * @returns {void}
 */
function onPointerEnd(event) {
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) {
        return;
    }
    state.drag = null;
    drag.chip.classList.remove("pdfe-chip-dragging");
    if (drag.chip.hasPointerCapture(event.pointerId)) {
        drag.chip.releasePointerCapture(event.pointerId);
    }
    if (drag.moved) {
        state.suppressClick = true;
        markDirty();
    }
}

/**
 * Captures what is visible at the center of the screen as a fraction of the page frame.
 * @returns {Point} Fractions from 0 to 1 of the frame width and height.
 */
function captureViewCenter() {
    const frame = dom.frame.getBoundingClientRect();
    const stage = dom.stage.getBoundingClientRect();
    const centerX = stage.left + stage.width / 2;
    const centerY = window.innerHeight / 2;
    return {
        x: frame.width ? clamp((centerX - frame.left) / frame.width, 0, 1) : 0.5,
        y: frame.height ? clamp((centerY - frame.top) / frame.height, 0, 1) : 0.5,
    };
}

/**
 * Scrolls so that a fraction of the page frame is back at the center of the screen.
 * @param {Point} fraction Fractions from 0 to 1 of the frame width and height.
 * @returns {void}
 */
function restoreViewCenter(fraction) {
    const frame = dom.frame.getBoundingClientRect();
    const stage = dom.stage.getBoundingClientRect();
    const centerX = stage.left + stage.width / 2;
    const centerY = window.innerHeight / 2;
    dom.stage.scrollLeft += frame.left + fraction.x * frame.width - centerX;
    window.scrollBy({ top: frame.top + fraction.y * frame.height - centerY, behavior: "instant" });
}

/**
 * Applies a zoom level keeping the center of the view where it was.
 * @param {number} index Index in ZOOM_STEPS.
 * @returns {void}
 */
function setZoom(index) {
    if (!state.pdfPage || index === state.zoomIndex || index < 0 || index >= ZOOM_STEPS.length) {
        return;
    }
    const center = captureViewCenter();
    state.zoomIndex = index;
    layoutPage();
    restoreViewCenter(center);
    updateToolbar();
    positionPanel();
    paintPage();
}

/**
 * Zooms out one level.
 * @returns {void}
 */
function onZoomOut() {
    setZoom(state.zoomIndex - 1);
}

/**
 * Zooms in one level.
 * @returns {void}
 */
function onZoomIn() {
    setZoom(state.zoomIndex + 1);
}

/**
 * Fits the page to the available width.
 * @returns {void}
 */
function onZoomFit() {
    setZoom(FIT_INDEX);
}

/**
 * Shows a page: measures its reference grid, sizes the frame, shows its texts and paints it.
 * @param {number} number Page number, starting at 1.
 * @returns {Promise<void>} Resolves when the page is painted or replaced by a newer request.
 */
async function showPage(number) {
    const doc = state.doc;
    if (!doc) {
        return;
    }
    state.pageTicket += 1;
    const ticket = state.pageTicket;
    dom.frame.dataset.state = "rendering";
    let pdfPage;
    try {
        pdfPage = await doc.getPage(number);
    } catch {
        showFeedback(PAGE_ERROR_MESSAGE, "error");
        return;
    }
    if (ticket !== state.pageTicket) {
        return;
    }
    const reference = pdfPage.getViewport({ scale: REF_SCALE });
    state.grids[number] = { width: Math.trunc(reference.width), height: Math.trunc(reference.height) };
    closePanel(false);
    state.page = number;
    state.pdfPage = pdfPage;
    layoutPage();
    renderChips();
    updateToolbar();
    await paintPage();
}

/**
 * Goes to the previous page.
 * @returns {void}
 */
function onPrevious() {
    if (state.page > 1) {
        showPage(state.page - 1);
    }
}

/**
 * Goes to the next page.
 * @returns {void}
 */
function onNext() {
    if (state.page < state.pageCount) {
        showPage(state.page + 1);
    }
}

/**
 * Fits the page again when the available width changed, keeping the zoom level.
 * @returns {void}
 */
function onStageResize() {
    if (!state.pdfPage || Math.floor(measureAvailableWidth()) === Math.floor(state.availableWidth)) {
        return;
    }
    layoutPage();
    positionPanel();
    paintPage();
}

/**
 * Builds the payload of the save request: one entry per annotation, in creation order.
 * @returns {Object[]} Annotations with text, x, y, fontSize, color, page, canvasWidth and canvasHeight.
 */
function buildPayload() {
    const annotations = [];
    for (const annotation of state.annotations) {
        const grid = state.grids[annotation.page];
        annotations.push({
            text: annotation.text,
            x: roundPosition(annotation.x),
            y: roundPosition(annotation.y),
            fontSize: annotation.size,
            color: toRgbString(annotation.color),
            page: annotation.page,
            canvasWidth: grid.width,
            canvasHeight: grid.height,
        });
    }
    return annotations;
}

/**
 * Switches the save button between its normal and saving states.
 * @param {boolean} saving True while the request is in flight.
 * @returns {void}
 */
function setSaving(saving) {
    state.saving = saving;
    dom.save.disabled = saving;
    dom.save.setAttribute("aria-busy", String(saving));
    dom.save.setAttribute("aria-label", saving ? "Salvando alterações no PDF" : "Salvar alterações no PDF");
    dom.saveLabel.textContent = saving ? "Salvando..." : "Salvar";
}

/**
 * Reads the JSON body of a response.
 * @param {Response} response Response of the save request.
 * @returns {Promise<{status?: string, message?: string, download_url?: string, redirect_url?: string} | null>} The body, or null when it is not JSON.
 */
async function readJson(response) {
    try {
        return await response.json();
    } catch {
        return null;
    }
}

/**
 * Opens the result dialog with the generated PDF.
 * @param {{download_url?: string, redirect_url?: string}} result Answer of the server.
 * @returns {void}
 */
function openResult(result) {
    const downloadUrl = result.download_url || "#";
    dom.resultDownload.href = downloadUrl;
    dom.resultFinish.href = result.redirect_url || "/";
    const separator = downloadUrl.includes("?") ? "&" : "?";
    if (!dom.result.open) {
        dom.result.showModal();
    }
    state.resultViewer = mountViewer(dom.resultViewer, `${downloadUrl}${separator}v=${Date.now()}`);
}

/**
 * Frees the viewer of the result dialog once it closes.
 * @returns {void}
 */
function onResultClose() {
    if (state.resultViewer) {
        state.resultViewer.destroy();
        state.resultViewer = null;
    }
}

/**
 * Closes the result dialog and keeps editing.
 * @returns {void}
 */
function onResultContinue() {
    dom.result.close();
}

/**
 * Sends the annotations to the server and shows the generated PDF.
 * @returns {Promise<void>} Resolves when the request is finished.
 */
async function onSave() {
    if (state.saving || !state.pdfPage) {
        return;
    }
    clearFeedback();
    if (state.annotations.length === 0) {
        showFeedback(EMPTY_SAVE_MESSAGE, "error");
        return;
    }
    closePanel(false);
    setSaving(true);
    try {
        const response = await fetch(dom.root.dataset.saveUrl || "", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ annotations: buildPayload() }),
        });
        const result = await readJson(response);
        if (response.ok && result && result.status === "success") {
            state.dirty = false;
            openResult(result);
        } else {
            showFeedback((result && result.message) || SAVE_ERROR_MESSAGE, "error");
        }
    } catch {
        showFeedback(NETWORK_ERROR_MESSAGE, "error");
    } finally {
        setSaving(false);
    }
}

/**
 * Asks the browser to confirm leaving while there are changes that were not saved.
 * @param {BeforeUnloadEvent} event Event of the page unload.
 * @returns {void}
 */
function onBeforeUnload(event) {
    if (!state.dirty) {
        return;
    }
    event.preventDefault();
    event.returnValue = "";
}

/**
 * Shows the message of a PDF that could not be loaded.
 * @returns {void}
 */
function showLoadError() {
    dom.root.dataset.state = "error";
    dom.frame.hidden = true;
    dom.status.textContent = LOAD_ERROR_MESSAGE;
}

/**
 * Loads the PDF and shows its first page.
 * @returns {Promise<void>} Resolves when the first page is painted.
 */
async function loadDocument() {
    const source = openPdf(dom.root.dataset.pdfUrl || "");
    try {
        state.doc = await source.promise;
    } catch {
        showLoadError();
        return;
    }
    state.pageCount = state.doc.numPages;
    dom.status.hidden = true;
    dom.save.disabled = false;
    await showPage(1);
}

/**
 * Connects the elements of the editor to their handlers.
 * @returns {void}
 */
function bindEvents() {
    dom.prev.addEventListener("click", onPrevious);
    dom.next.addEventListener("click", onNext);
    dom.zoomOut.addEventListener("click", onZoomOut);
    dom.zoomIn.addEventListener("click", onZoomIn);
    dom.zoomFit.addEventListener("click", onZoomFit);
    dom.save.addEventListener("click", onSave);
    dom.frame.addEventListener("click", onFrameClick);
    dom.frame.addEventListener("keydown", onFrameKeydown);
    dom.frame.addEventListener("pointerdown", onPointerDown);
    dom.frame.addEventListener("pointermove", onPointerMove);
    dom.frame.addEventListener("pointerup", onPointerEnd);
    dom.frame.addEventListener("pointercancel", onPointerEnd);
    dom.panel.addEventListener("submit", onPanelSubmit);
    dom.textInput.addEventListener("input", onTextInput);
    dom.cancel.addEventListener("click", onPanelCancel);
    dom.remove.addEventListener("click", onPanelRemove);
    dom.nudge.addEventListener("click", onNudge);
    dom.resultContinue.addEventListener("click", onResultContinue);
    dom.result.addEventListener("close", onResultClose);
    document.addEventListener("keydown", onDocumentKeydown);
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("resize", onViewportResize);
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", onViewportResize);
        window.visualViewport.addEventListener("scroll", onViewportScroll);
    }
    new ResizeObserver(onStageResize).observe(dom.stage);
}

/**
 * Starts the editor on the page that declares it.
 * @returns {void}
 */
function init() {
    const root = document.getElementById("pdfe-root");
    if (!root) {
        return;
    }
    dom = collectDom(root);
    renderer = createCanvasRenderer(dom.canvas);
    bindEvents();
    loadDocument();
}

init();
