document.addEventListener("DOMContentLoaded", function () {
    // Sanitize CPF
    const cpfInput = document.getElementById("cpf");
    cpfInput.addEventListener("blur", function () {
        // Get only digits
        let cpf = cpfInput.value.replace(/\D/g, "");
        if (/[a-zA-Z]/.test(cpfInput.value)) {
            alert("CPF inválido. Não pode conter letras.");
            cpfInput.value = "";
            return;
        }
        else if (cpf.length !== 11) {
            alert("CPF inválido. Precisa conter 11 dígitos.");
            cpfInput.value = "";
            return;
        }
        else if (cpf.length === 11) {
            cpfInput.value = cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
        }
    });

    // Sanitize Tel Number
    const phoneInput = document.getElementById("phone") || document.getElementById("tel_number");
    phoneInput.addEventListener("blur", function () {
        let phone = phoneInput.value.replace(/\D/g, "");
        // Format according to size:
        // 10 digits: (00) 0000-0000
        // 11 digits: (00) 00000-0000
        if (/[a-zA-Z]/.test(phoneInput.value)) {
            alert("Telefone inválido. Não pode conter letras.");
            phoneInput.value = "";
            return;
        } else if (phone.length < 10 || phone.length > 11) {
            alert("Telefone inválido. Precisa conter 10 ou 11 dígitos.");
            phoneInput.value = "";
            return;
        }

        if (phone.length === 10) {
            phoneInput.value = phone.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
        } else if (phone.length === 11) {
            phoneInput.value = phone.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
        }
    });

    // Validate email before submiting the form
    const form = document.querySelector("form");
    form.addEventListener("submit", function (e) {
        let email = emailInput.value.trim().toLowerCase();
        if (email.indexOf('@') === -1 || email.indexOf('.') === -1) {
            alert("Email inválido.");
            emailInput.focus();
            e.preventDefault();
        }
    });
});
