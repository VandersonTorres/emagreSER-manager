/**
 * Shows the dependent fields of the patient edit form only when they apply.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Tells whether any field inside an element holds a value other than empty or zero.
     * @param {Element} wrapper Element that wraps the fields of a group.
     * @returns {boolean} True when the group already has data.
     */
    function hasContent(wrapper) {
        const fields = wrapper.querySelectorAll("input, select, textarea");
        for (const field of fields) {
            const value = /** @type {HTMLInputElement} */ (field).value.trim();
            if (value !== "" && value !== "0") {
                return true;
            }
        }
        return false;
    }

    /**
     * Shows a dependent group when its select is "sim" or when the group already holds data.
     * @param {HTMLElement} wrapper Element marked with data-depends-on.
     * @returns {void}
     */
    function syncGroup(wrapper) {
        const select = /** @type {HTMLSelectElement | null} */ (document.getElementById(wrapper.dataset.dependsOn || ""));
        if (!select) {
            return;
        }
        wrapper.hidden = !(select.value === "sim" || hasContent(wrapper));
    }

    /**
     * Builds the listener that reapplies a group when its select changes.
     * @param {HTMLElement} wrapper Dependent group of the select.
     * @returns {() => void} The change listener.
     */
    function createChangeListener(wrapper) {
        /**
         * Shows or hides the group after the answer changed.
         * @returns {void}
         */
        function onChange() {
            syncGroup(wrapper);
        }
        return onChange;
    }

    /**
     * Applies the visibility of every dependent group and listens to the selects that drive them.
     * @returns {void}
     */
    function init() {
        const wrappers = /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("[data-depends-on]"));
        for (const wrapper of wrappers) {
            syncGroup(wrapper);
            const select = document.getElementById(wrapper.dataset.dependsOn || "");
            if (select) {
                select.addEventListener("change", createChangeListener(wrapper));
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
