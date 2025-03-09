// Function to toggle the patients view and initiate pagination
function togglePatients(event) {
    event.preventDefault();
    var listings = document.getElementById("patients-list");
    var toggleLink = document.getElementById("toggle-patients");

    if (listings.style.display === "none" || listings.style.display === "") {
        listings.style.display = "block";
        paginateList(); // Setup pagination when showing the list
        toggleLink.textContent = "Esconder pacientes";
    } else {
        listings.style.display = "none";
        var totalPatients = document.querySelectorAll("#patients-list ul li").length;
        toggleLink.textContent = "Mostrar " + totalPatients + " pacientes";
    }
}

// Setup pagination: divides patients into pages and creates the controls
function paginateList() {
    var listItems = document.querySelectorAll("#patients-list ul li");
    var itemsPerPage = 10; // Show 10 patients per page
    window.totalPatients = listItems.length;
    window.itemsPerPage = itemsPerPage;
    window.totalPages = Math.ceil(listItems.length / itemsPerPage);

    var paginationDiv = document.getElementById("pagination-controls");
    // Clear previous content
    paginationDiv.innerHTML = "";

    // Create container for pagination info (top)
    var paginationInfo = document.createElement("div");
    paginationInfo.id = "pagination-info";
    paginationDiv.appendChild(paginationInfo);

    // Create container for pagination buttons (bottom)
    var paginationButtons = document.createElement("div");
    paginationButtons.id = "pagination-buttons";
    paginationDiv.appendChild(paginationButtons);

    // If there is only one page, show all items and update info
    if (window.totalPages <= 1) {
        listItems.forEach(function(item) {
            item.style.display = "";
        });
        updatePaginationInfo(1, window.totalPatients);
        return;
    }

    // Show the first page by default
    showPage(1);
}

// Show items of the selected page and update controls
function showPage(page) {
    window.currentPage = page;
    var listItems = document.querySelectorAll("#patients-list ul li");
    var start = (page - 1) * window.itemsPerPage;
    var end = page * window.itemsPerPage;

    listItems.forEach(function(item, index) {
        if (index >= start && index < end) {
            item.style.display = "";
        } else {
            item.style.display = "none";
        }
    });
    updatePaginationInfo(page, window.totalPatients);
    updatePaginationButtons(page, window.totalPages);
}

// Update pagination info (top) showing current page and total patients
function updatePaginationInfo(page, totalPatients) {
    var paginationInfo = document.getElementById("pagination-info");
    if (paginationInfo) {
        paginationInfo.textContent = "Página " + page + " de " + window.totalPages + " - Total de pacientes: " + totalPatients;
    }
}
patients
// Update pagination buttons (bottom), grouping them in groups of 3
function updatePaginationButtons(currentPage, totalPages) {
    var paginationButtons = document.getElementById("pagination-buttons");
    paginationButtons.innerHTML = "";

    var groupSize = 3;
    // Calculate current group start and end
    var groupStart = Math.floor((currentPage - 1) / groupSize) * groupSize + 1;
    var groupEnd = Math.min(groupStart + groupSize - 1, totalPages);

    // If there is a previous group, add a "Previous" button to go to the previous group
    if (groupStart > 1) {
        var prevBtn = document.createElement("button");
        prevBtn.textContent = "Previous";
        prevBtn.addEventListener("click", function() {
            // Jump to the last page of the previous group
            showPage(groupStart - 1);
        });
        paginationButtons.appendChild(prevBtn);
    }

    // Create buttons for each page in the current group
    for (var i = groupStart; i <= groupEnd; i++) {
        var btn = document.createElement("button");
        btn.textContent = i;
        btn.setAttribute("data-page", i);
        if (i === currentPage) {
            btn.style.fontWeight = "bold"; // Highlight the current page
        }
        btn.addEventListener("click", function() {
            var pageNum = parseInt(this.getAttribute("data-page"));
            showPage(pageNum);
        });
        paginationButtons.appendChild(btn);
    }

    // If there is a subsequent group, add "Next" and "Last" buttons
    if (groupEnd < totalPages) {
        var nextBtn = document.createElement("button");
        nextBtn.textContent = "Next";
        nextBtn.addEventListener("click", function() {
            showPage(groupEnd + 1);
        });
        paginationButtons.appendChild(nextBtn);

        var lastBtn = document.createElement("button");
        lastBtn.textContent = "Last";
        lastBtn.addEventListener("click", function() {
            showPage(totalPages);
        });
        paginationButtons.appendChild(lastBtn);
    }
}

// Redirect to anthropometric evaluation
function redirectAnthro(event) {
    event.preventDefault();
    var select = document.getElementById("patient_select");
    var id = select.value;
    if (id) {
        window.location.href = addAnthroUrlTemplate.replace("0", id);
    } else {
        alert("Please select a patient.");
    }
}

// Redirect to skinfold evaluation
function redirectSkinfold(event) {
    event.preventDefault();
    var select = document.getElementById("patient_select_skinfold");
    var id = select.value;
    if (id) {
        window.location.href = addSkinfoldUrlTemplate.replace("0", id);
    } else {
        alert("Please select a patient.");
    }
}
