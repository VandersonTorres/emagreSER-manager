/**
 * Diet list: reorders the diets by dragging their handle or with the keyboard, and fills the single send dialog.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Text shown after the new order was stored.
     * @type {string}
     */
    const ORDER_SAVED = "Nova ordem salva.";

    /**
     * Text shown when the new order could not be stored.
     * @type {string}
     */
    const ORDER_FAILED = "Não foi possível salvar a nova ordem. Atualize a página e tente novamente.";

    /**
     * Text shown when a send button is pressed without a patient.
     * @type {string}
     */
    const PATIENT_REQUIRED = "Selecione um paciente.";

    /**
     * Selector of the handle that starts a drag.
     * @type {string}
     */
    const HANDLE_SELECTOR = ".diet-handle";

    /**
     * Whether the send form was already submitted, so a second tap cannot send the diet twice.
     * @type {{submitting: boolean}}
     */
    const sendState = { submitting: false };

    /**
     * Finds the list of diets.
     * @returns {HTMLElement | null} The list, or null when the page has no diets.
     */
    function getList() {
        return document.getElementById("diet-list");
    }

    /**
     * Builds the payload that stores the order of the diets as they appear in the list.
     * @param {HTMLElement} list List of diets.
     * @returns {{id: string | undefined, position: number}[]} One entry per diet, with its position from 1.
     */
    function buildOrder(list) {
        /**
         * Describes the position of one diet.
         * @param {Element} item List item of the diet.
         * @param {number} index Position of the item in the list, from 0.
         * @returns {{id: string | undefined, position: number}} The id of the diet and its position from 1.
         */
        function toEntry(item, index) {
            return { id: /** @type {HTMLElement} */ (item).dataset.id, position: index + 1 };
        }
        return Array.from(list.children).map(toEntry);
    }

    /**
     * Shows the result of storing the order in the live region of the page.
     * @param {string} message Text to announce.
     * @param {boolean} failed Whether the text reports a failure.
     * @returns {void}
     */
    function showOrderStatus(message, failed) {
        const status = document.getElementById("diet-order-status");
        if (!status) {
            return;
        }
        status.textContent = message;
        status.classList.toggle("is-error", failed);
    }

    /**
     * Posts the order of the list to the server and reports the result.
     * @param {HTMLElement} list List of diets, whose data-reorder-url holds the address.
     * @returns {Promise<void>} Resolves once the result was shown.
     */
    function saveOrder(list) {
        const url = list.dataset.reorderUrl || "";

        /**
         * Reads the answer of the server as JSON.
         * @param {Response} response Answer of the order request.
         * @returns {Promise<boolean>} True when the server stored the order.
         */
        function readAnswer(response) {
            /**
             * Tells whether the answer reports a stored order.
             * @param {{status?: string}} data Body of the answer.
             * @returns {boolean} True when the server stored the order.
             */
            function isStored(data) {
                return response.ok && data.status === "success";
            }
            return response.json().then(isStored);
        }

        /**
         * Announces whether the order was stored.
         * @param {boolean} saved Whether the server stored the order.
         * @returns {void}
         */
        function announce(saved) {
            showOrderStatus(saved ? ORDER_SAVED : ORDER_FAILED, !saved);
        }

        /**
         * Announces the failure of a request that did not reach the server or got an unreadable answer.
         * @returns {void}
         */
        function announceFailure() {
            showOrderStatus(ORDER_FAILED, true);
        }

        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order: buildOrder(list) }),
        })
            .then(readAnswer)
            .then(announce)
            .catch(announceFailure);
    }

    /**
     * Turns the list into a sortable list whose diets move only by their handle, so a swipe elsewhere scrolls the page.
     * @param {HTMLElement} list List of diets.
     * @returns {void}
     */
    function initSortable(list) {
        const Sortable = /** @type {any} */ (window).Sortable;
        if (!Sortable || list.dataset.reorderable !== "true") {
            return;
        }

        /**
         * Stores the order when a diet ended in another position.
         * @param {{oldIndex: number | undefined, newIndex: number | undefined}} event Event of the end of the drag.
         * @returns {void}
         */
        function onEnd(event) {
            if (event.oldIndex !== event.newIndex) {
                saveOrder(list);
            }
        }

        new Sortable(list, {
            handle: HANDLE_SELECTOR,
            animation: 150,
            ghostClass: "diet-card-ghost",
            chosenClass: "diet-card-chosen",
            dragClass: "diet-card-drag",
            onEnd: onEnd,
        });
    }

    /**
     * Moves a diet up or down with the arrow keys while its handle has the focus, and stores the new order.
     * @param {HTMLElement} list List of diets.
     * @returns {void}
     */
    function initKeyboardReorder(list) {
        if (list.dataset.reorderable !== "true") {
            return;
        }

        /**
         * Swaps the diet of the focused handle with its neighbour.
         * @param {KeyboardEvent} event Key press inside the list.
         * @returns {void}
         */
        function onKeydown(event) {
            const handle = /** @type {HTMLElement} */ (event.target).closest(HANDLE_SELECTOR);
            if (!handle || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) {
                return;
            }
            event.preventDefault();
            const item = /** @type {HTMLElement} */ (handle.closest("li"));
            const neighbour = event.key === "ArrowUp" ? item.previousElementSibling : item.nextElementSibling;
            if (!neighbour) {
                return;
            }
            if (event.key === "ArrowUp") {
                list.insertBefore(item, neighbour);
            } else {
                list.insertBefore(neighbour, item);
            }
            /** @type {HTMLElement} */ (handle).focus();
            saveOrder(list);
        }

        list.addEventListener("keydown", onKeydown);
    }

    /**
     * Shows or clears the message under the patient select of the send dialog.
     * @param {string} message Text to show, or an empty string to clear it.
     * @returns {void}
     */
    function setSendError(message) {
        const target = document.getElementById("send-diet-error");
        const select = document.getElementById("send-diet-patient");
        if (target) {
            target.textContent = message;
        }
        if (select) {
            select.setAttribute("aria-invalid", message ? "true" : "false");
        }
    }

    /**
     * Clears the message under the patient select of the send dialog.
     * @returns {void}
     */
    function clearSendError() {
        setSendError("");
    }

    /**
     * Enables or disables the two send buttons of the dialog.
     * @param {boolean} disabled Whether the buttons must be disabled.
     * @returns {void}
     */
    function setSendButtonsDisabled(disabled) {
        for (const id of ["send-diet-whatsapp", "send-diet-email"]) {
            const button = /** @type {HTMLButtonElement | null} */ (document.getElementById(id));
            if (button) {
                button.disabled = disabled;
            }
        }
        const form = document.getElementById("send-diet-form");
        if (form) {
            form.setAttribute("aria-busy", disabled ? "true" : "false");
        }
        sendState.submitting = disabled;
    }

    /**
     * Fills the send dialog with the diet of the button that opened it.
     * @param {Event} event The show event of the dialog, whose related target is the send button of a diet.
     * @returns {void}
     */
    function fillSendDialog(event) {
        const trigger = /** @type {HTMLElement | null} */ (/** @type {any} */ (event).relatedTarget);
        if (!trigger) {
            return;
        }
        const name = document.getElementById("send-diet-name");
        const whatsapp = document.getElementById("send-diet-whatsapp");
        const email = document.getElementById("send-diet-email");
        const preview = document.getElementById("send-diet-preview");
        if (name) {
            name.textContent = trigger.dataset.dietName || "";
        }
        if (whatsapp) {
            whatsapp.setAttribute("formaction", trigger.dataset.whatsappAction || "");
        }
        if (email) {
            email.setAttribute("formaction", trigger.dataset.emailAction || "");
        }
        if (preview) {
            preview.setAttribute("href", trigger.dataset.editionUrl || "#");
        }
    }

    /**
     * Clears the patient and the message of the send dialog, and releases the buttons, after it closed.
     * @returns {void}
     */
    function resetSendDialog() {
        const select = document.getElementById("send-diet-patient");
        if (select && window.jQuery) {
            window.jQuery(select).val("").trigger("change");
        }
        setSendError("");
        setSendButtonsDisabled(false);
    }

    /**
     * Checks the patient and locks the buttons when the send form is submitted.
     * @param {Event} event Submit event of the send form.
     * @returns {void}
     */
    function onSendSubmit(event) {
        if (sendState.submitting) {
            event.preventDefault();
            return;
        }
        const select = /** @type {HTMLSelectElement | null} */ (document.getElementById("send-diet-patient"));
        if (!select || !select.value) {
            event.preventDefault();
            setSendError(PATIENT_REQUIRED);
            const selection = document.querySelector("#send-diet-modal .select2-selection");
            if (selection) {
                /** @type {HTMLElement} */ (selection).focus();
            }
            return;
        }
        setSendError("");
        setSendButtonsDisabled(true);
    }

    /**
     * Releases the buttons when the browser shows the page again from its cache after a send.
     * @param {PageTransitionEvent} event The pageshow event.
     * @returns {void}
     */
    function onPageShow(event) {
        if (event.persisted) {
            resetSendDialog();
        }
    }

    /**
     * Prepares the send dialog: the searchable patient select, the diet it shows and the single submission.
     * @returns {void}
     */
    function initSendDialog() {
        const modal = document.getElementById("send-diet-modal");
        const form = document.getElementById("send-diet-form");
        const select = document.getElementById("send-diet-patient");
        if (!modal || !form || !select) {
            return;
        }
        if (window.jQuery && window.jQuery.fn.select2) {
            window.jQuery(select).select2({
                dropdownParent: window.jQuery(modal),
                placeholder: "Selecione ou digite o nome do paciente",
                allowClear: true,
            });
            window.jQuery(select).on("change", clearSendError);
        }
        modal.addEventListener("show.bs.modal", fillSendDialog);
        modal.addEventListener("hidden.bs.modal", resetSendDialog);
        form.addEventListener("submit", onSendSubmit);
        window.addEventListener("pageshow", onPageShow);
    }

    /**
     * Prepares the reordering and the send dialog once the page is ready.
     * @returns {void}
     */
    function init() {
        const list = getList();
        if (list) {
            initSortable(list);
            initKeyboardReorder(list);
        }
        initSendDialog();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
