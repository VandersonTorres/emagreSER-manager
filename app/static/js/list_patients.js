/**
 * Paginates the patient list and drives the evaluation and bioimpedance shortcuts.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Number of patients shown on each page of the list.
     * @type {number}
     */
    const ITEMS_PER_PAGE = 10;

    /**
     * Number of page buttons shown at a time.
     * @type {number}
     */
    const GROUP_SIZE = 3;

    /**
     * Pagination state of the list.
     * @type {{page: number, totalPages: number, totalPatients: number}}
     */
    const state = { page: 1, totalPages: 1, totalPatients: 0 };

    /**
     * Finds the patient items of the list.
     * @returns {HTMLElement[]} The direct list items of the patient list.
     */
    function getItems() {
        return Array.from(document.querySelectorAll("#patients-list > ul > li"));
    }

    /**
     * Creates a button of the pagination controls.
     * @param {string} label Visible text of the button.
     * @param {() => void} onClick Handler run when the button is pressed.
     * @param {boolean} [current] Whether the button is the current page.
     * @returns {HTMLButtonElement} The new button.
     */
    function createButton(label, onClick, current) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = current ? "btn btn-primary btn-sm" : "btn btn-outline-secondary btn-sm";
        button.textContent = label;
        if (current) {
            button.setAttribute("aria-current", "page");
        }
        button.addEventListener("click", onClick);
        return button;
    }

    /**
     * Shows the summary of the current page above the buttons.
     * @returns {void}
     */
    function updatePaginationInfo() {
        const info = document.getElementById("pagination-info");
        if (info) {
            info.textContent = "Página " + state.page + " de " + state.totalPages + " - Total de pacientes: " + state.totalPatients;
        }
    }

    /**
     * Rebuilds the page buttons, grouped by GROUP_SIZE, with the previous, next and last shortcuts.
     * @returns {void}
     */
    function updatePaginationButtons() {
        const container = document.getElementById("pagination-buttons");
        if (!container) {
            return;
        }
        container.replaceChildren();
        const groupStart = Math.floor((state.page - 1) / GROUP_SIZE) * GROUP_SIZE + 1;
        const groupEnd = Math.min(groupStart + GROUP_SIZE - 1, state.totalPages);

        if (groupStart > 1) {
            container.appendChild(createButton("Anterior", createPageHandler(groupStart - 1)));
        }
        for (let number = groupStart; number <= groupEnd; number++) {
            container.appendChild(createButton(String(number), createPageHandler(number), number === state.page));
        }
        if (groupEnd < state.totalPages) {
            container.appendChild(createButton("Próxima", createPageHandler(groupEnd + 1)));
            container.appendChild(createButton("Última", createPageHandler(state.totalPages)));
        }
    }

    /**
     * Builds the handler that opens a given page.
     * @param {number} number Page to open.
     * @returns {() => void} The click handler.
     */
    function createPageHandler(number) {
        /**
         * Opens the page captured by the handler.
         * @returns {void}
         */
        function openPage() {
            showPage(number);
        }
        return openPage;
    }

    /**
     * Shows only the patients of a page and refreshes the controls.
     * @param {number} page Page number, starting at 1.
     * @returns {void}
     */
    function showPage(page) {
        state.page = page;
        const start = (page - 1) * ITEMS_PER_PAGE;
        const end = page * ITEMS_PER_PAGE;
        for (const [index, item] of getItems().entries()) {
            item.style.display = index >= start && index < end ? "" : "none";
        }
        updatePaginationInfo();
        updatePaginationButtons();
    }

    /**
     * Splits the list into pages and builds the pagination controls.
     * @returns {void}
     */
    function paginateList() {
        const controls = document.getElementById("pagination-controls");
        if (!controls) {
            return;
        }
        const items = getItems();
        state.totalPatients = items.length;
        state.totalPages = Math.max(1, Math.ceil(items.length / ITEMS_PER_PAGE));
        controls.replaceChildren();

        const info = document.createElement("div");
        info.id = "pagination-info";
        const buttons = document.createElement("div");
        buttons.id = "pagination-buttons";
        controls.appendChild(info);
        controls.appendChild(buttons);

        if (state.totalPages <= 1) {
            for (const item of items) {
                item.style.display = "";
            }
            state.page = 1;
            updatePaginationInfo();
            return;
        }
        showPage(1);
    }

    /**
     * Shows or clears the message under a quick form.
     * @param {HTMLFormElement} form Quick form that owns the message.
     * @param {string} message Text to show, or an empty string to clear it.
     * @returns {void}
     */
    function setQuickFormError(form, message) {
        const target = form.querySelector(".quick-form-error");
        if (target) {
            target.textContent = message;
        }
        const select = form.querySelector("select");
        if (select) {
            select.setAttribute("aria-invalid", message ? "true" : "false");
        }
    }

    /**
     * Opens the page that matches a quick form for the chosen patient.
     * @param {HTMLFormElement} form Quick form that was submitted.
     * @param {string} selectId Id of the select that holds the patient.
     * @param {string} urlTemplate URL with a 0 in the place of the patient id.
     * @returns {void}
     */
    function redirectToPatient(form, selectId, urlTemplate) {
        const select = /** @type {HTMLSelectElement | null} */ (document.getElementById(selectId));
        const id = select ? select.value : "";
        if (!id) {
            setQuickFormError(form, "Selecione um paciente.");
            return;
        }
        setQuickFormError(form, "");
        window.location.href = urlTemplate.replace("/0/", "/" + id + "/");
    }

    /**
     * Sends the user to the new evaluation page of the chosen patient.
     * @param {Event} event Submit event of the evaluation quick form.
     * @returns {void}
     */
    function redirectAnthro(event) {
        event.preventDefault();
        redirectToPatient(/** @type {HTMLFormElement} */ (event.currentTarget), "patient_select", window.addAnthroUrlTemplate);
    }

    /**
     * Sends the user to the new bioimpedance page of the chosen patient.
     * @param {Event} event Submit event of the bioimpedance quick form.
     * @returns {void}
     */
    function redirectSkinfold(event) {
        event.preventDefault();
        redirectToPatient(
            /** @type {HTMLFormElement} */ (event.currentTarget),
            "patient_select_skinfold",
            window.addSkinfoldUrlTemplate
        );
    }

    /**
     * Turns a patient select into a searchable select2 and clears its message when a patient is chosen.
     * @param {string} selectId Id of the select.
     * @returns {void}
     */
    function enhanceSelect(selectId) {
        const select = document.getElementById(selectId);
        if (!select || !window.jQuery || !window.jQuery.fn.select2) {
            return;
        }
        const $select = window.jQuery(select);
        $select.select2({ placeholder: "Selecione um paciente", allowClear: true });

        /**
         * Clears the message of the form that owns the select.
         * @returns {void}
         */
        function clearError() {
            const form = select.closest("form");
            if (form) {
                setQuickFormError(/** @type {HTMLFormElement} */ (form), "");
            }
        }
        $select.on("change", clearError);
    }

    /**
     * Prepares the pagination and the quick forms once the page is ready.
     * @returns {void}
     */
    function init() {
        paginateList();
        enhanceSelect("patient_select");
        enhanceSelect("patient_select_skinfold");
        const anthroForm = document.getElementById("anthro-form");
        if (anthroForm) {
            anthroForm.addEventListener("submit", redirectAnthro);
        }
        const skinfoldForm = document.getElementById("skinfold-form");
        if (skinfoldForm) {
            skinfoldForm.addEventListener("submit", redirectSkinfold);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
