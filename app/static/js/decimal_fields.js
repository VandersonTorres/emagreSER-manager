/**
 * Accepts a decimal comma in the editable decimal fields by turning it into a dot.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Replaces the first comma of a decimal field by a dot, so values typed with the pt-BR keyboard are accepted.
     * @this {HTMLInputElement}
     * @returns {void}
     */
    function normalizeDecimal() {
        if (this.value.includes(",")) {
            this.value = this.value.replace(",", ".");
        }
    }

    /**
     * Listens to every editable decimal field of the page.
     * @returns {void}
     */
    function init() {
        const fields = document.querySelectorAll('input[inputmode="decimal"]:not([readonly])');
        for (const field of fields) {
            field.addEventListener("input", normalizeDecimal);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
