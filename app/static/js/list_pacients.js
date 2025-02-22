// Redirects to anthro and skinfold managers

function redirectAnthro(event) {
    event.preventDefault();
    var select = document.getElementById("pacient_select");
    var id = select.value;
    if (id) {
        // Getting the global variable assigned in template
        window.location.href = addAnthroUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}

function redirectSkinfold(event) {
    event.preventDefault();
    var select = document.getElementById("pacient_select_skinfold");
    var id = select.value;
    if (id) {
        window.location.href = addSkinfoldUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}
