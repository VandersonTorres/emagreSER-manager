/**
 * Drives the patient record: age, tabs kept in the URL hash, show-more buttons, delete confirmations and the dialog
 * with the observation of the latest bioimpedance.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Key of the tab opened when nothing else says which one to open.
     * @type {string}
     */
    const DEFAULT_TAB = "dados";

    /**
     * Prefix of the session storage key that remembers the tab of a patient record.
     * @type {string}
     */
    const STORAGE_PREFIX = "patient-tab:";

    /**
     * Id of the dialog that shows the observation of the latest bioimpedance.
     * @type {string}
     */
    const NOTE_MODAL_ID = "note-modal";

    /**
     * Id of the heading that receives the focus when the observation dialog closes.
     * @type {string}
     */
    const NOTE_RETURN_FOCUS_ID = "patient-name";

    /**
     * Pages that lead back to a given tab of the record after saving.
     * @type {Array<{fragments: string[], tab: string}>}
     */
    const REFERRER_TABS = [
        { fragments: ["/anthropometric/add", "/anthro/edit/"], tab: "avaliacoes" },
        { fragments: ["/skinfolds/add", "/skinfolds/edit/"], tab: "bioimpedancia" },
    ];

    /**
     * Finds the button of a tab by its key.
     * @param {string} key Tab key, such as "avaliacoes".
     * @returns {HTMLElement | null} The tab button, or null when the key is unknown.
     */
    function findTabButton(key) {
        return document.querySelector('#patient-tabs [data-tab-key="' + key + '"]');
    }

    /**
     * Reads a value from the session storage without failing when the storage is blocked.
     * @param {string} key Storage key.
     * @returns {string | null} The stored value, or null.
     */
    function readStorage(key) {
        try {
            return window.sessionStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    /**
     * Writes a value to the session storage without failing when the storage is blocked.
     * @param {string} key Storage key.
     * @param {string} value Value to store.
     * @returns {void}
     */
    function writeStorage(key, value) {
        try {
            window.sessionStorage.setItem(key, value);
        } catch (error) {
            return;
        }
    }

    /**
     * Works out which tab a saved form or a delete sends the user back to, from the page that came before.
     * @returns {string | null} The tab key, or null when the previous page says nothing about it.
     */
    function tabFromReferrer() {
        if (!document.referrer) {
            return null;
        }
        let referrer;
        try {
            referrer = new URL(document.referrer);
        } catch (error) {
            return null;
        }
        if (referrer.origin !== window.location.origin) {
            return null;
        }
        for (const rule of REFERRER_TABS) {
            for (const fragment of rule.fragments) {
                if (referrer.pathname.includes(fragment)) {
                    return rule.tab;
                }
            }
        }
        if (referrer.pathname === window.location.pathname) {
            return readStorage(STORAGE_PREFIX + window.location.pathname);
        }
        return null;
    }

    /**
     * Chooses the tab to open when the page loads: the one in the URL hash, then the one the previous page implies.
     * @returns {string} The tab key.
     */
    function initialTabKey() {
        const fromHash = window.location.hash.replace("#", "");
        if (fromHash && findTabButton(fromHash)) {
            return fromHash;
        }
        const fromReferrer = tabFromReferrer();
        if (fromReferrer && findTabButton(fromReferrer)) {
            return fromReferrer;
        }
        return DEFAULT_TAB;
    }

    /**
     * Shows a tab through Bootstrap.
     * @param {string} key Tab key.
     * @returns {void}
     */
    function showTab(key) {
        const button = findTabButton(key);
        if (button && window.bootstrap) {
            window.bootstrap.Tab.getOrCreateInstance(button).show();
        }
    }

    /**
     * Makes the charts fit the container that just became visible.
     * @returns {void}
     */
    function resizeCharts() {
        if (!window.Chart) {
            return;
        }
        for (const canvas of document.querySelectorAll("canvas[data-weights]")) {
            const chart = window.Chart.getChart(canvas);
            if (chart) {
                chart.resize();
            }
        }
    }

    /**
     * Keeps the URL hash and the session storage in step with the tab that was just shown.
     * @param {Event} event The shown.bs.tab event.
     * @returns {void}
     */
    function onTabShown(event) {
        const button = /** @type {HTMLElement} */ (event.target);
        const key = button.dataset.tabKey;
        if (!key) {
            return;
        }
        window.history.replaceState(null, "", "#" + key);
        writeStorage(STORAGE_PREFIX + window.location.pathname, key);
        resizeCharts();
    }

    /**
     * Opens the tab named by the URL hash after the hash changes.
     * @returns {void}
     */
    function onHashChange() {
        const key = window.location.hash.replace("#", "");
        if (key) {
            showTab(key);
        }
    }

    /**
     * Wires the tabs: opens the initial one and keeps the hash updated.
     * @returns {void}
     */
    function initTabs() {
        const nav = document.getElementById("patient-tabs");
        if (!nav) {
            return;
        }
        nav.addEventListener("shown.bs.tab", onTabShown);
        window.addEventListener("hashchange", onHashChange);
        const key = initialTabKey();
        if (key !== DEFAULT_TAB) {
            showTab(key);
        }
    }

    /**
     * Switches a table between its first rows and all of its rows.
     * @this {HTMLButtonElement}
     * @returns {void}
     */
    function toggleRows() {
        const table = document.getElementById(this.dataset.table || "");
        if (!table) {
            return;
        }
        const expanded = table.classList.toggle("is-expanded");
        this.setAttribute("aria-expanded", expanded ? "true" : "false");
        this.textContent = (expanded ? this.dataset.less : this.dataset.more) || "";
    }

    /**
     * Makes the "show more" buttons expand their tables.
     * @returns {void}
     */
    function initToggles() {
        for (const button of document.querySelectorAll("button[data-table]")) {
            button.addEventListener("click", toggleRows);
        }
    }

    /**
     * Asks for confirmation before a form that carries a data-confirm message is sent.
     * @param {Event} event Submit event.
     * @returns {void}
     */
    function confirmSubmit(event) {
        const form = event.target;
        if (form instanceof HTMLFormElement && form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
            event.preventDefault();
        }
    }

    /**
     * Calculates the age in whole years.
     * @param {string} birth Birth date as YYYY-MM-DD.
     * @param {Date} today Reference date.
     * @returns {number} The age in years.
     */
    function calculateAge(birth, today) {
        const [year, month, day] = birth.split("-").map(Number);
        const currentMonth = today.getMonth() + 1;
        let age = today.getFullYear() - year;
        if (currentMonth < month || (currentMonth === month && today.getDate() < day)) {
            age -= 1;
        }
        return age;
    }

    /**
     * Writes the age of the patient next to the birth date.
     * @returns {void}
     */
    function showAge() {
        const target = /** @type {HTMLElement | null} */ (document.querySelector(".patient-age[data-birth-date]"));
        if (!target || !target.dataset.birthDate) {
            return;
        }
        const age = calculateAge(target.dataset.birthDate, new Date());
        if (Number.isNaN(age) || age < 0) {
            return;
        }
        target.textContent = " · " + (age === 1 ? "1 ano" : age + " anos");
    }

    /**
     * Moves the focus to the button that closes the observation dialog once it is fully shown.
     * @param {Event} event The shown.bs.modal event.
     * @returns {void}
     */
    function focusAcknowledgeButton(event) {
        const dialog = /** @type {HTMLElement} */ (event.target);
        const button = /** @type {HTMLElement | null} */ (dialog.querySelector(".modal-footer .btn-primary"));
        if (button) {
            button.focus();
        }
    }

    /**
     * Gives the focus back to the page, on the patient name, after the observation dialog closes.
     * @returns {void}
     */
    function returnFocusToPage() {
        const heading = document.getElementById(NOTE_RETURN_FOCUS_ID);
        if (heading) {
            heading.focus({ preventScroll: true });
        }
    }

    /**
     * Opens the dialog with the observation of the latest bioimpedance, which the server only renders when it exists.
     * @returns {void}
     */
    function initNoteModal() {
        const dialog = document.getElementById(NOTE_MODAL_ID);
        if (!dialog || !window.bootstrap) {
            return;
        }
        dialog.addEventListener("shown.bs.modal", focusAcknowledgeButton);
        dialog.addEventListener("hidden.bs.modal", returnFocusToPage);
        window.bootstrap.Modal.getOrCreateInstance(dialog).show();
    }

    /**
     * Prepares the patient record once the page is ready.
     * @returns {void}
     */
    function init() {
        showAge();
        initToggles();
        initTabs();
        initNoteModal();
        document.addEventListener("submit", confirmSubmit);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
