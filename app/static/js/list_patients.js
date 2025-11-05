document.addEventListener("DOMContentLoaded", function () {
    const tableBody = document.querySelector("table tbody");
    if (tableBody) {
        paginateTable();
    }
});

// === PAGINATION ===
function paginateTable() {
    const rows = document.querySelectorAll("table tbody tr");
    const itemsPerPage = 5;
    window.totalPatients = rows.length;
    window.itemsPerPage = itemsPerPage;
    window.totalPages = Math.ceil(rows.length / itemsPerPage);

    const paginationDiv = document.getElementById("pagination-controls");
    paginationDiv.innerHTML = "";

    const paginationInfo = document.createElement("div");
    paginationInfo.id = "pagination-info";
    paginationInfo.classList.add("text-center", "mb-2", "text-muted");
    paginationDiv.appendChild(paginationInfo);

    const paginationButtons = document.createElement("nav");
    paginationButtons.id = "pagination-buttons";
    paginationButtons.setAttribute("aria-label", "Paginação de pacientes");
    paginationDiv.appendChild(paginationButtons);

    if (window.totalPages <= 1) {
        rows.forEach(row => row.style.display = "");
        updatePaginationInfo(1, window.totalPatients);
        return;
    }

    showPage(1);
}

// Show items of the selected page and update controls
function showPage(page) {
    window.currentPage = page;
    const rows = document.querySelectorAll("table tbody tr");
    const start = (page - 1) * window.itemsPerPage;
    const end = page * window.itemsPerPage;

    rows.forEach((row, index) => {
        row.style.display = (index >= start && index < end) ? "" : "none";
    });

    updatePaginationButtons(page, window.totalPages);
}

function updatePaginationButtons(currentPage, totalPages) {
    const paginationNav = document.getElementById("pagination-buttons");
    paginationNav.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.classList.add("d-flex", "flex-column", "align-items-center", "gap-2", "mt-3");

    // Pagination info
    const info = document.createElement("div");
    info.classList.add("text-muted", "small");
    info.textContent = `Página ${currentPage} de ${totalPages} — Total de pacientes: ${window.totalPatients}`;
    wrapper.appendChild(info);

    // Pagination buttons list
    const ul = document.createElement("ul");
    ul.classList.add("pagination", "justify-content-center", "mb-0", "flex-wrap");

    const createPageItem = (label, page, disabled = false, active = false) => {
        const li = document.createElement("li");
        li.classList.add("page-item");
        if (disabled) li.classList.add("disabled");
        if (active) li.classList.add("active");

        const a = document.createElement("a");
        a.classList.add("page-link");
        a.href = "#";
        a.textContent = label;

        if (!disabled && !active) {
            a.addEventListener("click", (e) => {
                e.preventDefault();
                showPage(page);
            });
        }

        li.appendChild(a);
        return li;
    };

    // === Button "Primeira Página" ===
    if (currentPage > 1) {
        ul.appendChild(createPageItem("««", 1));
    } else {
        ul.appendChild(createPageItem("««", 1, true));
    }

    // Button "Anterior"
    ul.appendChild(createPageItem("«", currentPage - 1, currentPage === 1));

    // Show up to 10 pages at a time
    const maxVisible = 10;
    let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    if (end - start < maxVisible - 1) start = Math.max(1, end - maxVisible + 1);

    for (let i = start; i <= end; i++) {
        ul.appendChild(createPageItem(i, i, false, i === currentPage));
    }

    // Button "Próxima"
    ul.appendChild(createPageItem("»", currentPage + 1, currentPage === totalPages));

    // === Button "Última Página" ===
    if (currentPage < totalPages) {
        ul.appendChild(createPageItem("»»", totalPages));
    } else {
        ul.appendChild(createPageItem("»»", totalPages, true));
    }

    wrapper.appendChild(ul);
    paginationNav.appendChild(wrapper);
}

// === REDIRECTS ===
function redirectAnthro(event) {
    event.preventDefault();
    const select = document.getElementById("patient_select");
    const id = select.value;
    if (id) {
        window.location.href = addAnthroUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}

function redirectSkinfold(event) {
    event.preventDefault();
    const select = document.getElementById("patient_select_skinfold");
    const id = select.value;
    if (id) {
        window.location.href = addSkinfoldUrlTemplate.replace("0", id);
    } else {
        alert("Por favor, selecione um paciente.");
    }
}
