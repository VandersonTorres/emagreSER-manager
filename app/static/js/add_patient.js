/**
 * Shows the conditional answers of the new patient form and keeps their required state in step.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * A group of fields shown only when a yes/no select is answered "sim".
     * @typedef {Object} ConditionalRule
     * @property {string} select Id of the yes/no select.
     * @property {string} group Id of the element that wraps the fields of the group.
     * @property {string[]} required Ids of the fields that are required while the group is visible.
     * @property {string[]} clear Ids of the fields emptied when the group is hidden.
     */

    /**
     * Conditional groups of the new patient form.
     * @type {ConditionalRule[]}
     */
    const RULES = [
        {
            select: "medication",
            group: "medications_details_group",
            required: ["medications_details"],
            clear: ["medications_details"],
        },
        {
            select: "allergies",
            group: "allergies_details_group",
            required: ["allergies_details"],
            clear: ["allergies_details"],
        },
        {
            select: "physical_activities",
            group: "physical_details_group",
            required: ["physical_details"],
            clear: [],
        },
        {
            select: "physical_activities",
            group: "physical_extras",
            required: ["hours", "frequency"],
            clear: [],
        },
    ];

    /**
     * Finds a form control by id.
     * @param {string} id Element id.
     * @returns {HTMLInputElement | null} The control, or null when the page does not have it.
     */
    function findField(id) {
        return /** @type {HTMLInputElement | null} */ (document.getElementById(id));
    }

    /**
     * Shows or hides a group of fields according to its select, keeping the required state in step.
     * @param {ConditionalRule} rule Rule to apply.
     * @param {boolean} clearWhenHidden Whether hiding the group also empties its text fields.
     * @returns {void}
     */
    function applyRule(rule, clearWhenHidden) {
        const select = findField(rule.select);
        const group = document.getElementById(rule.group);
        if (!select || !group) {
            return;
        }
        const visible = select.value === "sim";
        group.hidden = !visible;
        for (const id of rule.required) {
            const field = findField(id);
            if (field) {
                field.required = visible;
            }
        }
        if (!visible && clearWhenHidden) {
            for (const id of rule.clear) {
                const field = findField(id);
                if (field) {
                    field.value = "";
                }
            }
        }
    }

    /**
     * Builds the listener that reapplies a rule when its select changes.
     * @param {ConditionalRule} rule Rule bound to the select.
     * @returns {() => void} The change listener.
     */
    function createChangeListener(rule) {
        /**
         * Reapplies the rule, emptying the fields that become hidden.
         * @returns {void}
         */
        function onChange() {
            applyRule(rule, true);
        }
        return onChange;
    }

    /**
     * Applies every rule to the loaded form and listens to the selects.
     * @returns {void}
     */
    function init() {
        for (const rule of RULES) {
            applyRule(rule, false);
            const select = findField(rule.select);
            if (select) {
                select.addEventListener("change", createChangeListener(rule));
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
