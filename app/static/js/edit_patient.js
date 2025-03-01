// Show and Hide fields dynamically

function toggleField(fieldId) {
    let fieldDiv = document.getElementById("field_" + fieldId);
    let checkbox = document.getElementById("check_" + fieldId);
    let inputField = fieldDiv.querySelector("input, select, textarea");

    if (checkbox.checked) {
        // Store the original value the first time the field is edited
        if (!inputField.dataset.originalValue) {
            inputField.dataset.originalValue = inputField.value;
        }
        // Show and allow editing
        fieldDiv.style.display = "block";
        inputField.removeAttribute("readonly");
        inputField.setAttribute("required", "");
    } else {
        // Restore the original value and hide field
        inputField.value = inputField.dataset.originalValue || "";
        fieldDiv.style.display = "none";
        inputField.setAttribute("readonly", "true");
    }
}
