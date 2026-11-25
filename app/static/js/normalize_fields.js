/**
 * Cleans and validates the CPF, phone and e-mail fields of the patient and specialist forms.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Shows the validation bubble once per edit, or every time when the form is being submitted.
     * @param {HTMLInputElement} input Field that was validated.
     * @param {boolean} onSubmit Whether the validation runs because the form is being submitted.
     * @returns {void}
     */
    function reportOnce(input, onSubmit) {
        if (!input.dataset.validated || onSubmit) {
            input.reportValidity();
            input.dataset.validated = "true";
        }
    }

    /**
     * Cleans and validates a CPF field, formatting it as 000.000.000-00 when it has 11 digits.
     * @param {HTMLInputElement} input CPF field.
     * @param {boolean} [onSubmit] Whether the validation runs because the form is being submitted.
     * @returns {void}
     */
    function validateCPF(input, onSubmit = false) {
        if (input.value.trim() === "") {
            input.setCustomValidity("");
            return;
        }

        let cpf = input.value.replace(/\D/g, "");
        if (cpf.length > 11) {
            cpf = cpf.slice(0, 11);
            input.value = cpf;
        }

        if (/[a-zA-Z]/.test(input.value)) {
            input.setCustomValidity("CPF inválido. Não pode conter letras.");
            input.value = "";
        } else if (cpf.length !== 11) {
            input.setCustomValidity("CPF inválido. Precisa conter 11 dígitos.");
            input.value = "";
        } else {
            input.setCustomValidity("");
            input.value = cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
        }

        reportOnce(input, onSubmit);
    }

    /**
     * Cleans and validates a phone field, formatting it as (00) 0000-0000 or (00) 00000-0000.
     * @param {HTMLInputElement} input Phone field.
     * @param {boolean} [onSubmit] Whether the validation runs because the form is being submitted.
     * @returns {void}
     */
    function validatePhone(input, onSubmit = false) {
        let phone = input.value.replace(/\D/g, "");
        if (phone.length > 11) {
            phone = phone.slice(0, 11);
            input.value = phone;
        }
        if (!onSubmit && input.value.trim() === "") {
            input.setCustomValidity("");
            return;
        }

        if (/[a-zA-Z]/.test(input.value)) {
            input.setCustomValidity("Telefone inválido. Não pode conter letras.");
            input.value = "";
        } else if (phone.length < 10 || phone.length > 11) {
            input.setCustomValidity("Telefone inválido. Precisa conter 10 ou 11 dígitos.");
            input.value = "";
        } else {
            input.setCustomValidity("");
            if (phone.length === 10) {
                input.value = phone.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
            } else if (phone.length === 11) {
                input.value = phone.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
            }
        }

        reportOnce(input, onSubmit);
    }

    /**
     * Validates an e-mail field; an empty field is left to the required attribute of the form.
     * @param {HTMLInputElement} input E-mail field.
     * @param {boolean} [onSubmit] Whether the validation runs because the form is being submitted.
     * @returns {void}
     */
    function validateEmail(input, onSubmit = false) {
        const email = input.value.trim().toLowerCase();
        if (email === "") {
            input.setCustomValidity("");
            return;
        }

        if (!email.match(/^[^@]+@[^@]+\.[a-z]{2,}$/i)) {
            input.setCustomValidity("Email inválido.");
            input.value = "";
        } else {
            input.setCustomValidity("");
        }

        reportOnce(input, onSubmit);
    }

    /**
     * Builds the blur listener that runs a validation function on a field.
     * @param {HTMLInputElement} input Field to validate.
     * @param {(input: HTMLInputElement, onSubmit?: boolean) => void} validate Validation function.
     * @returns {() => void} The blur listener.
     */
    function createBlurListener(input, validate) {
        /**
         * Validates the field when it loses focus.
         * @returns {void}
         */
        function onBlur() {
            validate(input);
        }
        return onBlur;
    }

    /**
     * Resets the "already reported" mark of a field after the user edits it.
     * @this {HTMLInputElement}
     * @returns {void}
     */
    function resetValidated() {
        this.dataset.validated = "";
    }

    /**
     * Validates a field when it loses focus and shows its message again after each edit.
     * @param {HTMLInputElement} input Field to watch.
     * @param {(input: HTMLInputElement, onSubmit?: boolean) => void} validate Validation function.
     * @returns {void}
     */
    function setupValidation(input, validate) {
        input.addEventListener("input", resetValidated);
        input.addEventListener("blur", createBlurListener(input, validate));
    }

    /**
     * Builds the submit listener that normalizes the known fields and blocks the submit when any field is invalid.
     * @param {HTMLFormElement} form Form that owns the fields.
     * @param {HTMLInputElement | null} cpfInput CPF field, when the form has one.
     * @param {HTMLInputElement | null} phoneInput Phone field, when the form has one.
     * @param {HTMLInputElement | null} emailInput E-mail field, when the form has one.
     * @returns {(event: Event) => void} The submit listener.
     */
    function createSubmitListener(form, cpfInput, phoneInput, emailInput) {
        /**
         * Validates the known fields and cancels the submit when a field of the form is invalid.
         * @param {Event} event Submit event.
         * @returns {void}
         */
        function onSubmit(event) {
            let valid = true;

            if (cpfInput) validateCPF(cpfInput, true);
            if (phoneInput) validatePhone(phoneInput, true);
            if (emailInput) validateEmail(emailInput, true);

            for (const input of form.querySelectorAll("input")) {
                if (!input.checkValidity()) {
                    valid = false;
                }
            }

            if (!valid) {
                event.preventDefault();
            }
        }
        return onSubmit;
    }

    /**
     * Attaches the validations to the CPF, phone and e-mail fields of the page.
     * @returns {void}
     */
    function init() {
        const cpfInput = /** @type {HTMLInputElement | null} */ (document.getElementById("cpf"));
        if (cpfInput) setupValidation(cpfInput, validateCPF);

        const phoneInput = /** @type {HTMLInputElement | null} */ (
            document.getElementById("phone") || document.getElementById("tel_number")
        );
        if (phoneInput) setupValidation(phoneInput, validatePhone);

        const emailInput = /** @type {HTMLInputElement | null} */ (document.getElementById("email"));
        if (emailInput) setupValidation(emailInput, validateEmail);

        const anchor = cpfInput || phoneInput || emailInput;
        const form = anchor ? anchor.form : document.querySelector("form");
        if (form) {
            form.addEventListener("submit", createSubmitListener(form, cpfInput, phoneInput, emailInput));
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
