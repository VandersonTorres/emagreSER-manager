/**
 * @typedef {Object} PdfViewport
 * @property {number} width Width of the page in CSS pixels at the requested scale.
 * @property {number} height Height of the page in CSS pixels at the requested scale.
 */

/**
 * @typedef {Object} PdfRenderTask
 * @property {Promise<void>} promise Settles when the page is painted, or rejects when the task is cancelled.
 * @property {function(): void} cancel Stops the task.
 */

/**
 * @typedef {Object} PdfPage
 * @property {function({scale: number}): PdfViewport} getViewport Measures the page at a scale.
 * @property {function({canvasContext: CanvasRenderingContext2D, viewport: PdfViewport}): PdfRenderTask} render Paints the page.
 */

/**
 * @typedef {Object} PdfDocument
 * @property {number} numPages Number of pages of the document.
 * @property {function(number): Promise<PdfPage>} getPage Loads a page by its 1-based number.
 */

/**
 * @typedef {Object} PdfSource
 * @property {Promise<PdfDocument>} promise Resolves with the loaded document.
 * @property {function(): void} destroy Aborts the loading and frees the document.
 */

/**
 * @typedef {Object} CanvasRenderer
 * @property {function(PdfPage, number): Promise<boolean>} render Paints a page at a CSS width; resolves false when a newer call replaced it.
 * @property {function(): void} cancel Stops the current painting.
 */

/**
 * @typedef {Object} PdfViewerHandle
 * @property {Promise<void>} ready Resolves when the first page is painted, rejects when the PDF cannot be loaded.
 * @property {function(): void} destroy Removes the viewer and frees the PDF.
 */

/**
 * Largest bitmap, in pixels, a canvas may get; keeps phones inside their canvas memory limit.
 * @type {number}
 */
const MAX_CANVAS_PIXELS = 16000000;

/**
 * Smallest pixel ratio of a bitmap, so extreme zoom levels still paint something.
 * @type {number}
 */
const MIN_PIXEL_RATIO = 0.25;

/**
 * Message shown when a PDF cannot be loaded.
 * @type {string}
 */
const LOAD_ERROR_MESSAGE = "Não foi possível carregar o PDF. Atualize a página e tente novamente.";

/**
 * Returns the pdf.js library loaded by the page.
 * @returns {{getDocument: function({url: string}): {promise: Promise<PdfDocument>, destroy: function(): void}}} The pdf.js namespace.
 */
function getPdfjs() {
    return /** @type {any} */ (window).pdfjsLib;
}

/**
 * Does nothing; stands in for the abort of a PDF that never started loading.
 * @returns {void}
 */
function doNothing() {}

/**
 * Starts loading a PDF; a missing or broken pdf.js yields a source whose promise rejects instead of throwing.
 * @param {string} url Address of the PDF file.
 * @returns {PdfSource} The pending document and a way to abort it.
 */
export function openPdf(url) {
    /** @type {{promise: Promise<PdfDocument>, destroy: function(): void}} */
    let task;
    try {
        task = getPdfjs().getDocument({ url });
    } catch (error) {
        return { promise: Promise.reject(error), destroy: doNothing };
    }

    /**
     * Aborts the loading and frees the document.
     * @returns {void}
     */
    function destroy() {
        task.destroy();
    }

    return { promise: task.promise, destroy };
}

/**
 * Picks how many bitmap pixels each CSS pixel gets: the device pixel ratio, lowered for very large pages.
 * @param {number} cssWidth Displayed width of the page in CSS pixels.
 * @param {number} cssHeight Displayed height of the page in CSS pixels.
 * @returns {number} Bitmap pixels per CSS pixel.
 */
function pickPixelRatio(cssWidth, cssHeight) {
    const wanted = Math.max(1, window.devicePixelRatio || 1);
    const limit = Math.sqrt(MAX_CANVAS_PIXELS / (cssWidth * cssHeight));
    return Math.max(MIN_PIXEL_RATIO, Math.min(wanted, limit));
}

/**
 * Tells whether an error is the one pdf.js raises when a painting is cancelled on purpose.
 * @param {unknown} error Error caught while waiting for a render task.
 * @returns {boolean} True for a cancelled rendering.
 */
function isCancelled(error) {
    return Boolean(error) && /** @type {{name?: string}} */ (error).name === "RenderingCancelledException";
}

/**
 * Creates a renderer that paints PDF pages sharply on one canvas, one painting at a time.
 *
 * A page is painted on a hidden canvas first and copied in one step, so the visible canvas never flashes blank when
 * the size changes. A newer call cancels the previous one.
 * @param {HTMLCanvasElement} canvas Canvas that shows the page.
 * @returns {CanvasRenderer} The renderer.
 */
export function createCanvasRenderer(canvas) {
    const buffer = document.createElement("canvas");
    /** @type {PdfRenderTask | null} */
    let task = null;
    let ticket = 0;

    /**
     * Stops the current painting, if any.
     * @returns {void}
     */
    function cancel() {
        ticket += 1;
        if (task) {
            task.cancel();
        }
    }

    /**
     * Paints a page at a displayed width.
     * @param {PdfPage} page Page to paint.
     * @param {number} cssWidth Displayed width of the page in CSS pixels.
     * @returns {Promise<boolean>} True when this call painted the canvas, false when a newer call replaced it.
     */
    async function render(page, cssWidth) {
        ticket += 1;
        const mine = ticket;
        if (task) {
            task.cancel();
            try {
                await task.promise;
            } catch (error) {
                if (!isCancelled(error)) {
                    throw error;
                }
            }
        }
        if (mine !== ticket) {
            return false;
        }
        const natural = page.getViewport({ scale: 1 });
        const ratio = pickPixelRatio(cssWidth, (cssWidth * natural.height) / natural.width);
        const viewport = page.getViewport({ scale: (cssWidth * ratio) / natural.width });
        buffer.width = Math.max(1, Math.round(viewport.width));
        buffer.height = Math.max(1, Math.round(viewport.height));
        const context = /** @type {CanvasRenderingContext2D} */ (buffer.getContext("2d"));
        task = page.render({ canvasContext: context, viewport });
        try {
            await task.promise;
        } catch (error) {
            if (isCancelled(error)) {
                return false;
            }
            throw error;
        }
        if (mine !== ticket) {
            return false;
        }
        canvas.width = buffer.width;
        canvas.height = buffer.height;
        /** @type {CanvasRenderingContext2D} */ (canvas.getContext("2d")).drawImage(buffer, 0, 0);
        return true;
    }

    return { render, cancel };
}

/**
 * Creates an element with a class name.
 * @param {string} tag Tag name.
 * @param {string} className Class names, separated by spaces.
 * @returns {HTMLElement} The new element.
 */
function createElement(tag, className) {
    const element = document.createElement(tag);
    element.className = className;
    return element;
}

/**
 * Creates an icon button of the viewer toolbar.
 * @param {string} icon Bootstrap Icons name, without the "bi-" prefix.
 * @param {string} label Accessible name of the button.
 * @returns {HTMLButtonElement} The new button.
 */
function createIconButton(icon, label) {
    const button = /** @type {HTMLButtonElement} */ (createElement("button", "btn btn-outline-secondary pdfv-button"));
    button.type = "button";
    button.setAttribute("aria-label", label);
    const glyph = createElement("i", `bi bi-${icon}`);
    glyph.setAttribute("aria-hidden", "true");
    button.append(glyph);
    return button;
}

/**
 * Builds a PDF viewer inside an element: fit to width, sharp on high density screens, previous and next page.
 * @param {HTMLElement} root Element that receives the viewer.
 * @param {string} url Address of the PDF file.
 * @returns {PdfViewerHandle} Handle to wait for the first page and to remove the viewer.
 */
export function mountViewer(root, url) {
    root.classList.add("pdfv");
    root.dataset.state = "loading";
    root.replaceChildren();

    const toolbar = createElement("div", "pdfv-toolbar");
    toolbar.setAttribute("role", "group");
    toolbar.setAttribute("aria-label", "Navegação entre páginas");
    const previous = createIconButton("chevron-left", "Página anterior");
    const next = createIconButton("chevron-right", "Próxima página");
    const info = createElement("span", "pdfv-info");
    info.setAttribute("aria-live", "polite");
    previous.disabled = true;
    next.disabled = true;
    toolbar.append(previous, info, next);

    const wrap = createElement("div", "pdfv-page");
    const canvas = /** @type {HTMLCanvasElement} */ (createElement("canvas", "pdfv-canvas"));
    wrap.append(canvas);

    const status = createElement("p", "pdfv-status");
    status.setAttribute("role", "status");
    status.textContent = "Carregando o PDF...";

    root.append(toolbar, wrap, status);

    const renderer = createCanvasRenderer(canvas);
    const source = openPdf(url);
    /** @type {PdfDocument | null} */
    let pdf = null;
    let pageNumber = 1;
    let pageCount = 0;
    let shown = 0;
    let renderedWidth = 0;
    let destroyed = false;

    /**
     * Updates the page label and the state of the navigation buttons.
     * @returns {void}
     */
    function refreshToolbar() {
        info.textContent = `Página ${pageNumber} de ${pageCount}`;
        previous.disabled = pageNumber <= 1;
        next.disabled = pageNumber >= pageCount;
    }

    /**
     * Paints the current page at the width of the viewer.
     * @returns {Promise<void>} Resolves when the page is painted or replaced by a newer request.
     */
    async function showPage() {
        if (!pdf || destroyed) {
            return;
        }
        shown += 1;
        const mine = shown;
        refreshToolbar();
        const page = await pdf.getPage(pageNumber);
        if (mine !== shown || destroyed) {
            return;
        }
        renderedWidth = Math.floor(wrap.clientWidth);
        const painted = await renderer.render(page, renderedWidth);
        if (painted && !destroyed) {
            root.dataset.state = "ready";
            root.dataset.page = String(pageNumber);
        }
    }

    /**
     * Goes to the previous page.
     * @returns {void}
     */
    function goPrevious() {
        if (pageNumber > 1) {
            pageNumber -= 1;
            showPage();
        }
    }

    /**
     * Goes to the next page.
     * @returns {void}
     */
    function goNext() {
        if (pageNumber < pageCount) {
            pageNumber += 1;
            showPage();
        }
    }

    /**
     * Repaints the page when the viewer width changed.
     * @returns {void}
     */
    function onResize() {
        if (pdf && Math.floor(wrap.clientWidth) !== renderedWidth) {
            showPage();
        }
    }

    previous.addEventListener("click", goPrevious);
    next.addEventListener("click", goNext);
    const observer = new ResizeObserver(onResize);
    observer.observe(wrap);

    /**
     * Loads the document and paints its first page.
     * @returns {Promise<void>} Resolves when the first page is painted; rejects when the PDF cannot be loaded.
     */
    async function start() {
        try {
            pdf = await source.promise;
        } catch (error) {
            if (!destroyed) {
                root.dataset.state = "error";
                status.textContent = LOAD_ERROR_MESSAGE;
            }
            throw error;
        }
        if (destroyed) {
            return;
        }
        pageCount = pdf.numPages;
        status.hidden = true;
        await showPage();
    }

    /**
     * Removes the viewer and frees the PDF.
     * @returns {void}
     */
    function destroy() {
        destroyed = true;
        observer.disconnect();
        renderer.cancel();
        source.destroy();
        root.replaceChildren();
        root.classList.remove("pdfv");
        delete root.dataset.state;
        delete root.dataset.page;
    }

    /**
     * Swallows the failure of the first page here; callers that care wait on the returned promise.
     * @returns {void}
     */
    function ignoreFailure() {}

    const ready = start();
    ready.catch(ignoreFailure);
    return { ready, destroy };
}

/**
 * Mounts a viewer on every element that declares a PDF address in "data-pdf-viewer".
 * @returns {void}
 */
function initViewers() {
    /**
     * Mounts the viewer of one element.
     * @param {Element} element Element with the "data-pdf-viewer" attribute.
     * @returns {void}
     */
    function mount(element) {
        const host = /** @type {HTMLElement} */ (element);
        mountViewer(host, host.dataset.pdfViewer || "");
    }

    document.querySelectorAll("[data-pdf-viewer]").forEach(mount);
}

initViewers();
