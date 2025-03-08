// Display elements as needed

function toggleMedicationsInput(select) {
    const medDetails = document.getElementById('medications_details');
    if (select.value === "sim") {
        medDetails.style.display = "inline";
        medDetails.setAttribute("required", "required");
    } else {
        medDetails.style.display = "none";
        medDetails.removeAttribute("required");
        medDetails.value = "";
    }
}

function toggleAllergiesInput(select) {
    const allergiesDetails = document.getElementById('allergies_details');
    if (select.value === "sim") {
        allergiesDetails.style.display = "inline";
        allergiesDetails.setAttribute("required", "required");
    } else {
        allergiesDetails.style.display = "none";
        allergiesDetails.removeAttribute("required");
        allergiesDetails.value = "";
    }
}

function togglePhysicalInput(select) {
    const physical_details = document.getElementById('physical_details');
    const physical_extras = document.getElementById('physical_extras');

    if (select.value === "sim") {
        physical_details.style.display = "inline";
        physical_details.setAttribute("required", "required");
        physical_extras.style.display = "block";
        document.getElementById("hours").setAttribute("required", "required");
        document.getElementById("frequency").setAttribute("required", "required");
    } else {
        physical_details.style.display = "none";
        physical_details.removeAttribute("required");
        physical_extras.style.display = "none";
        document.getElementById("hours").removeAttribute("required");
        document.getElementById("frequency").removeAttribute("required");
    }
}
