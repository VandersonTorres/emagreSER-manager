// Show and Hide fields dinamically

function toggleField(fieldId) {
    let fieldDiv = document.getElementById("field_" + fieldId);
    let checkbox = document.getElementById("check_" + fieldId);
    let inputField = fieldDiv.querySelector("input, select, textarea");

    if (checkbox.checked) {
        // Show and allow edition
        fieldDiv.style.display = "block";
        inputField.removeAttribute("readonly");
    } else {
        // Hide field and keep the original value
        fieldDiv.style.display = "none";
        inputField.setAttribute("readonly", "true");
    }
}
