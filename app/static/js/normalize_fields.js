document.addEventListener("DOMContentLoaded", function () {
    function validateCPF(input, onSubmit = false) {
        let cpf = input.value.replace(/\D/g, "");
        if (!onSubmit && input.value.trim() === "") {
            input.setCustomValidity("");
            return;
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

        if (!input.dataset.validated || onSubmit) {
            input.reportValidity();
            input.dataset.validated = "true";
        }
    }

    function validatePhone(input, onSubmit = false) {
        let phone = input.value.replace(/\D/g, "");
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

        if (!input.dataset.validated || onSubmit) {
            input.reportValidity();
            input.dataset.validated = "true";
        }
    }

    function validateEmail(input, onSubmit = false) {
        let email = input.value.trim().toLowerCase();
        if (!onSubmit && email === "") {
            input.setCustomValidity("");
            return;
        }

        if (!email.match(/^[^@]+@[^@]+\.[a-z]{2,}$/i)) {
            input.setCustomValidity("Email inválido.");
            input.value = "";
        } else {
            input.setCustomValidity("");
        }

        if (!input.dataset.validated || onSubmit) {
            input.reportValidity();
            input.dataset.validated = "true";
        }
    }

    function setupValidation(input, validationFunction) {
        input.addEventListener("input", function () {
            input.dataset.validated = "";
        });
        input.addEventListener("blur", function () {
            validationFunction(input);
        });
    }

    const cpfInput = document.getElementById("cpf");
    if (cpfInput) setupValidation(cpfInput, validateCPF);

    const phoneInput = document.getElementById("phone") || document.getElementById("tel_number");
    if (phoneInput) setupValidation(phoneInput, validatePhone);

    const emailInput = document.getElementById("email");
    if (emailInput) setupValidation(emailInput, validateEmail);

    const form = document.querySelector("form");
    if (form) {
        form.addEventListener("submit", function (e) {
            let valid = true;

            if (cpfInput) validateCPF(cpfInput, true);
            if (phoneInput) validatePhone(phoneInput, true);
            if (emailInput) validateEmail(emailInput, true);

            document.querySelectorAll("input").forEach(input => {
                if (!input.checkValidity()) {
                    valid = false;
                }
            });

            if (!valid) {
                e.preventDefault();
            }
        });
    }
});
