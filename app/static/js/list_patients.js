// Redirects to anthro and skinfold managers

// Function to alternate patients view
function togglePatients(event) {
    event.preventDefault();
    var listings = document.getElementById("patients-list");
    var toggleLink = document.getElementById("toggle-patients");

    if (listings.style.display === "none" || listings.style.display === "") {
        listings.style.display = "block";
        toggleLink.textContent = "Esconder pacientes";
    } else {
        listings.style.display = "none";
        // Update the text with the total amount of patients
        var totalPatients = listings.querySelectorAll("li").length;
        toggleLink.textContent = "Mostrar " + totalPatients + " pacientes";
    }
}

// Redirects to anthro evaluation
function redirectAnthro(event) {
    event.preventDefault();
    var select = document.getElementById("patient_select");
    var id = select.value;
    if (id) {
        // Getting the global variables assigned in template
        window.location.href = addAnthroUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}

// Redirects to skinfolds
function redirectSkinfold(event) {
    event.preventDefault();
    var select = document.getElementById("patient_select_skinfold");
    var id = select.value;
    if (id) {
        window.location.href = addSkinfoldUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}
