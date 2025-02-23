// Display elements as needed

function toggleMedicationsInput(select) {
    document.getElementById('medications_details').style.display = select.value === "sim" ? "inline" : "none";
}
function toggleAllergiesInput(select) {
    document.getElementById('allergies_details').style.display = select.value === "sim" ? "inline" : "none";
}
function togglePhysicalInput(select) {
    document.getElementById('physical_details').style.display = select.value === "sim" ? "inline" : "none";
}
