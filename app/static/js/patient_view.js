document.addEventListener("DOMContentLoaded", function () {
    // Antropometria toggle
    const toggleAnthro = document.getElementById("toggleAnthro");
    let anthroExpanded = false;

    if (toggleAnthro) {
        toggleAnthro.addEventListener("click", function () {
            const hiddenRows = document.querySelectorAll(".anthro-row");
            hiddenRows.forEach((row, index) => {
                if (index >= 5) {
                    row.style.display = anthroExpanded ? "none" : "table-row";
                }
            });

            anthroExpanded = !anthroExpanded;
            toggleAnthro.textContent = anthroExpanded
                ? "Mostrar menos avaliações"
                : "Mostrar mais avaliações";
        });
    }

    // Bioimpedância toggle
    const toggleSkinfold = document.getElementById("toggleSkinfold");
    let skinfoldExpanded = false;

    if (toggleSkinfold) {
        toggleSkinfold.addEventListener("click", function () {
            const hiddenRows = document.querySelectorAll(".skinfold-row");
            hiddenRows.forEach((row, index) => {
                if (index >= 5) {
                    row.style.display = skinfoldExpanded ? "none" : "table-row";
                }
            });

            skinfoldExpanded = !skinfoldExpanded;
            toggleSkinfold.textContent = skinfoldExpanded
                ? "Mostrar menos medições"
                : "Mostrar mais medições";
        });
    }
});
