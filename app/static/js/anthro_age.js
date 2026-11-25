/**
 * Fills the age of the patient on the evaluation date of the evaluation forms.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Fills the age field with the age the patient has on the evaluation date.
     * @param {HTMLFormElement} form Evaluation form that carries the birth date in data-birth-date.
     * @returns {void}
     */
    function calculateAge(form) {
        const birthDate = form.dataset.birthDate;
        const dateField = /** @type {HTMLInputElement | null} */ (document.getElementById("data_avaliacao"));
        const ageField = /** @type {HTMLInputElement | null} */ (document.getElementById("idade"));
        if (!dateField || !ageField) {
            return;
        }
        const dataAvaliacao = dateField.value;
        if (birthDate && dataAvaliacao) {
            const birth = new Date(birthDate);
            const evaluation = new Date(dataAvaliacao);
            let years_old = evaluation.getFullYear() - birth.getFullYear();
            const current_month = evaluation.getMonth();
            const born_month = birth.getMonth();
            if (current_month < born_month || (current_month === born_month && evaluation.getDate() < birth.getDate())) {
                years_old--;
            }
            ageField.value = String(years_old);
        }
    }

    /**
     * Builds the listener that recalculates the age when the evaluation date changes.
     * @param {HTMLFormElement} form Evaluation form.
     * @returns {() => void} The change listener.
     */
    function createChangeListener(form) {
        /**
         * Recalculates the age after the date changed.
         * @returns {void}
         */
        function onChange() {
            calculateAge(form);
        }
        return onChange;
    }

    /**
     * Calculates the age on load and whenever the evaluation date changes.
     * @returns {void}
     */
    function init() {
        const form = /** @type {HTMLFormElement | null} */ (document.querySelector("form[data-birth-date]"));
        const dateField = document.getElementById("data_avaliacao");
        if (!form || !dateField) {
            return;
        }
        dateField.addEventListener("change", createChangeListener(form));
        calculateAge(form);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
