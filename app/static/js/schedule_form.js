/**
 * Booking form: makes the patient select searchable and shows a message under it when no patient was chosen.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Text shown when the form is submitted without a patient.
     * @type {string}
     */
    const PATIENT_REQUIRED = "Selecione um paciente.";

    /**
     * Shows or clears the message under the patient select.
     * @param {string} message Text to show, or an empty string to clear it.
     * @returns {void}
     */
    function setPatientError(message) {
        const target = document.getElementById("schedule-patient-error");
        const select = document.getElementById("schedule-patient");
        if (target) {
            target.textContent = message;
        }
        if (select) {
            select.setAttribute("aria-invalid", message ? "true" : "false");
        }
    }

    /**
     * Replaces the browser bubble by a message under the select and moves the focus to the searchable select.
     * @param {Event} event Invalid event of the patient select.
     * @returns {void}
     */
    function onPatientInvalid(event) {
        event.preventDefault();
        setPatientError(PATIENT_REQUIRED);
        const selection = document.querySelector(".add-schedule-form .select2-selection");
        if (selection) {
            /** @type {HTMLElement} */ (selection).focus();
        }
    }

    /**
     * Clears the message once a patient is chosen.
     * @returns {void}
     */
    function clearPatientError() {
        setPatientError("");
    }

    /**
     * Turns the patient select into a searchable select2 and wires its message.
     * @returns {void}
     */
    function init() {
        const select = document.getElementById("schedule-patient");
        if (!select || !window.jQuery || !window.jQuery.fn.select2) {
            return;
        }
        const $select = window.jQuery(select);
        $select.select2({ placeholder: "Selecione ou digite o nome do paciente", allowClear: true });
        $select.on("change", clearPatientError);
        select.addEventListener("invalid", onPatientInvalid);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
