document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("form");
    const emailInput = document.querySelector("input[name='email']");
    const passwordInput = document.querySelector("input[name='password']");

    form.addEventListener("submit", function (event) {
        const email = emailInput.value.trim();
        const password = passwordInput.value;

        // Validate e-mail
        const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailPattern.test(email)) {
            alert("Por favor, insira um e-mail válido!");
            event.preventDefault();
            return;
        }

        // Validate password
        const passwordPattern = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{6,}$/;
        if (!passwordPattern.test(password)) {
            alert("A senha não corresponde ao padrão solicitado");
            event.preventDefault();
            return;
        }
    });
});
