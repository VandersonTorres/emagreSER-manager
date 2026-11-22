/**
 * Time a non-critical toast stays visible before hiding itself, in milliseconds.
 * @type {number}
 */
const TOAST_AUTOHIDE_MS = 5000;

/**
 * Hides a toast through Bootstrap, or by removing the "show" class when Bootstrap is not available.
 * @param {HTMLElement} element Toast element to hide.
 * @returns {void}
 */
function hideToast(element) {
    if (typeof bootstrap !== "undefined") {
        bootstrap.Toast.getOrCreateInstance(element, { autohide: false }).hide();
        return;
    }
    element.classList.remove("show");
}

/**
 * Hides a toast after the delay, pausing the countdown while the pointer or the keyboard focus is on it.
 * @param {HTMLElement} element Toast element to hide automatically.
 * @returns {void}
 */
function scheduleAutoHide(element) {
    /** @type {number} */
    let timer = 0;

    /**
     * Hides the toast once the delay has elapsed.
     * @returns {void}
     */
    function hideAfterDelay() {
        hideToast(element);
    }

    /**
     * Starts the countdown from the beginning.
     * @returns {void}
     */
    function start() {
        window.clearTimeout(timer);
        timer = window.setTimeout(hideAfterDelay, TOAST_AUTOHIDE_MS);
    }

    /**
     * Stops the countdown.
     * @returns {void}
     */
    function pause() {
        window.clearTimeout(timer);
    }

    element.addEventListener("mouseenter", pause);
    element.addEventListener("focusin", pause);
    element.addEventListener("mouseleave", start);
    element.addEventListener("focusout", start);
    start();
}

/**
 * Prepares a rendered toast: removes it from the page once hidden and auto-hides it unless it is critical.
 * @param {HTMLElement} element Toast element rendered by the server.
 * @returns {void}
 */
function initToast(element) {
    /**
     * Removes the hidden toast from the page.
     * @returns {void}
     */
    function removeToast() {
        element.remove();
    }

    element.addEventListener("hidden.bs.toast", removeToast);
    if (element.dataset.autohide === "true") {
        scheduleAutoHide(element);
    }
}

/**
 * Initializes every toast rendered in the toast region.
 * @returns {void}
 */
function initToasts() {
    /**
     * Prepares one toast of the region.
     * @param {Element} element Toast element found in the region.
     * @returns {void}
     */
    function prepare(element) {
        initToast(/** @type {HTMLElement} */ (element));
    }

    document.querySelectorAll("#toast-region .toast").forEach(prepare);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initToasts);
} else {
    initToasts();
}
