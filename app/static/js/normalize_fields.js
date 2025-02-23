document.addEventListener("DOMContentLoaded", function () {
    // Sanitize CPF
    const cpfInput = document.getElementById("cpf");
    cpfInput.addEventListener("blur", function cpfHandler() {
        let cpf = cpfInput.value.replace(/\D/g, "");
        if (/[a-zA-Z]/.test(cpfInput.value)) {
            cpfInput.removeEventListener("blur", cpfHandler);   // Avoid alert loop
            cpfInput.value = "";
            alert("CPF inválido. Não pode conter letras.");
            cpfInput.addEventListener("blur", cpfHandler);      // Avoid alert loop
            return;
        } else if (cpf.length !== 11) {
            cpfInput.removeEventListener("blur", cpfHandler);
            cpfInput.value = "";
            alert("CPF inválido. Precisa conter 11 dígitos.");
            cpfInput.addEventListener("blur", cpfHandler);
            return;
        } else {
            cpfInput.value = cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
        }
    });

    // Sanitize Tel Number
    const phoneInput = document.getElementById("phone") || document.getElementById("tel_number");
    phoneInput.addEventListener("blur", function phoneHandler() {
        let phone = phoneInput.value.replace(/\D/g, "");
        if (/[a-zA-Z]/.test(phoneInput.value)) {
            phoneInput.removeEventListener("blur", phoneHandler);
            phoneInput.value = "";
            alert("Telefone inválido. Não pode conter letras.");
            phoneInput.addEventListener("blur", phoneHandler);
            return;
        } else if (phone.length < 10 || phone.length > 11) {
            phoneInput.removeEventListener("blur", phoneHandler);
            phoneInput.value = "";
            alert("Telefone inválido. Precisa conter 10 ou 11 dígitos.");
            phoneInput.addEventListener("blur", phoneHandler);
            return;
        }
        if (phone.length === 10) {
            phoneInput.value = phone.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
        } else if (phone.length === 11) {
            phoneInput.value = phone.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
        }
    });

    // Validate email before submitting the form
    const form = document.querySelector("form");
    const emailInput = document.getElementById("email");
    form.addEventListener("submit", function (e) {
        let email = emailInput.value.trim().toLowerCase();
        if (email.indexOf('@') === -1 || email.indexOf('.') === -1) {
            alert("Email inválido.");
            emailInput.focus();
            e.preventDefault();
        }
    });
});
