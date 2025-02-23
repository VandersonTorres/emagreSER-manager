// Allow defining other name to diets

document.addEventListener("DOMContentLoaded", function() {
    const selectField = document.getElementById("diet-select");
    const otherNameField = document.getElementById("other-name-field");

    function toggleOtherField() {
        if (selectField.value.toLowerCase() === "outro") {
            otherNameField.style.display = "block";
        } else {
            otherNameField.style.display = "none";
        }
    }

    selectField.addEventListener("change", toggleOtherField);
    toggleOtherField();
});

document.addEventListener("submit", function(event) {
    document.getElementById("ultima_guia").disabled = false;
});
