/**
 * Toggles the custom diet name field of the evaluation and diet forms.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Shows the field for a custom diet name only while "Outro" is the chosen diet.
     * @returns {void}
     */
    function toggleOtherField() {
        const selectField = /** @type {HTMLSelectElement | null} */ (document.getElementById("diet-select"));
        const otherNameField = document.getElementById("other-name-field");
        if (!selectField || !otherNameField) {
            return;
        }
        const other = selectField.value.toLowerCase() === "outro";
        otherNameField.hidden = !other;
        otherNameField.style.display = other ? "block" : "none";
    }

    /**
     * Re-enables the diet name field before the form is sent, when the page has one that was disabled.
     * @returns {void}
     */
    function enableDietName() {
        const dietName = /** @type {HTMLInputElement | null} */ (document.getElementById("ultima_guia"));
        if (dietName) {
            dietName.disabled = false;
        }
    }

    /**
     * Wires the diet select and the submit handler once the page is ready.
     * @returns {void}
     */
    function init() {
        const selectField = document.getElementById("diet-select");
        if (selectField) {
            selectField.addEventListener("change", toggleOtherField);
            toggleOtherField();
        }
        document.addEventListener("submit", enableDietName);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
