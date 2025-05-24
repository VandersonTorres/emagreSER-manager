let pdfDoc = null;
let currentPage = 1;
let totalPages = 0;
const scale = 1.64;
const canvas = document.getElementById("pdf-canvas");
const ctx = canvas.getContext("2d");
let currentEditingText = null;

pdfjsLib.getDocument(pdfUrl).promise.then(function (doc) {
    pdfDoc = doc;
    totalPages = doc.numPages;
    renderPage(currentPage);
});

function renderPage(pageNum) {
    pdfDoc.getPage(pageNum).then(function (page) {
        const viewport = page.getViewport({ scale: scale });
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        page.render({
            canvasContext: ctx,
            viewport: viewport,
        }).promise.then(() => {
            document.getElementById("page-info").textContent = `Página ${currentPage} de ${totalPages}`;
            loadAnnotationsForPage(currentPage);
        });
    });
}

document.getElementById("prev-page").addEventListener("click", () => {
    if (currentPage > 1) {
        currentPage--;
        renderPage(currentPage);
    }
});

document.getElementById("next-page").addEventListener("click", () => {
    if (currentPage < totalPages) {
        currentPage++;
        renderPage(currentPage);
    }
});

canvas.addEventListener("click", function (event) {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    openTextModal(x, y);
});

function openTextModal(x, y) {
    const modal = document.getElementById("text-modal");
    const editModal = document.getElementById("edit-text-modal");
    const canvasRect = canvas.getBoundingClientRect();

    if (editModal.style.display === "flex") editModal.style.display = "none";

    const absoluteX = canvasRect.left + x;
    const absoluteY = canvasRect.top + y;

    modal.style.display = "flex";
    modal.style.left = "0px";
    modal.style.top = "0px";
    modal.classList.add("show");

    document.getElementById("text-input").value = "";

    requestAnimationFrame(() => {
        const modalWidth = modal.offsetWidth;
        const modalHeight = modal.offsetHeight;
        modal.style.left = `${absoluteX - modalWidth / 2}px`;
        modal.style.top = `${absoluteY - modalHeight - 10}px`;
        document.getElementById("text-input").focus();
    });

    modal.dataset.x = x;
    modal.dataset.y = y;
    modal.dataset.page = currentPage;
}

document.getElementById("cancel-btn").addEventListener("click", () => {
    document.getElementById("text-modal").style.display = "none";
});

document.getElementById("add-text-btn").addEventListener("click", () => {
    const modal = document.getElementById("text-modal");
    const text = document.getElementById("text-input").value;
    const size = document.getElementById("text-size").value;
    const color = document.getElementById("text-color").value;
    const x = modal.dataset.x;
    const y = modal.dataset.y;
    const page = parseInt(modal.dataset.page);

    if (text.trim() !== "") {
        addTextToPDF(text, x, y, size, color, page);
    }

    modal.classList.remove("show");
    modal.style.display = "none";
});

function addTextToPDF(text, x, y, size, color, page) {
    const textDiv = document.createElement("div");
    textDiv.classList.add("draggable-text");
    textDiv.innerText = text;
    textDiv.style.position = "absolute";
    textDiv.style.left = parseFloat(x) + "px";
    textDiv.style.top = parseFloat(y) + "px";
    textDiv.style.fontSize = size + "px";
    textDiv.style.color = color;
    textDiv.dataset.page = page;
    textDiv.dataset.canvasWidth = canvas.width;
    textDiv.dataset.canvasHeight = canvas.height;

    makeDraggable(textDiv);

    textDiv.addEventListener("click", function (e) {
        e.stopPropagation();
        editOrRemoveText(textDiv);
    });

    document.getElementById("pdf-container").appendChild(textDiv);

    if (parseInt(page) !== currentPage) {
        textDiv.style.display = "none";
    }
}

function makeDraggable(el) {
    let offsetX, offsetY;
    el.addEventListener("mousedown", function (e) {
        offsetX = e.offsetX;
        offsetY = e.offsetY;

        function mouseMoveHandler(e) {
            const rect = canvas.getBoundingClientRect();
            el.style.left = e.clientX - rect.left - offsetX + "px";
            el.style.top = e.clientY - rect.top - offsetY + "px";
        }

        function mouseUpHandler() {
            document.removeEventListener("mousemove", mouseMoveHandler);
            document.removeEventListener("mouseup", mouseUpHandler);
        }

        document.addEventListener("mousemove", mouseMoveHandler);
        document.addEventListener("mouseup", mouseUpHandler);
    });
}

function getAnnotations() {
    const annotations = [];
    const canvasWidth = canvas.width;
    const canvasHeight = canvas.height;

    document.querySelectorAll('.draggable-text').forEach(el => {
        annotations.push({
            text: el.innerText,
            x: parseFloat(el.style.left),
            y: parseFloat(el.style.top),
            fontSize: parseInt(el.style.fontSize, 10),
            color: el.style.color,
            page: parseInt(el.dataset.page),
            canvasWidth: canvasWidth,
            canvasHeight: canvasHeight
        });
    });

    return annotations;
}

async function savePDF() {
    const annotations = getAnnotations();

    const response = await fetch(window.location.href, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ annotations }),
    });

    try {
        const result = await response.json();
        if (result.status === "success") {
            alert(result.message);
            const shouldDownload = confirm("Deseja baixar o PDF editado agora?");
            if (shouldDownload) {
                const link = document.createElement("a");
                link.href = result.download_url;
                link.setAttribute("download", "");
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }

            window.location.href = result.redirect_url;
        } else {
            alert(result.message || "Erro ao salvar.");
        }
    } catch (e) {
        console.error("Erro ao interpretar resposta:", e);
        alert("Erro inesperado ao processar a resposta.");
    }
}

document.getElementById("save-changes-btn").addEventListener("click", savePDF);

function editOrRemoveText(textDiv) {
    currentEditingText = textDiv;
    const modal = document.getElementById("edit-text-modal");
    const addModal = document.getElementById("text-modal");
    const canvasRect = canvas.getBoundingClientRect();
    const x = parseInt(textDiv.style.left, 10);
    const y = parseInt(textDiv.style.top, 10);

    if (addModal.style.display === "flex") addModal.style.display = "none";

    let absoluteX = canvasRect.left + x;
    let absoluteY = canvasRect.top + y;

    modal.style.display = "flex";
    modal.style.left = "0px";
    modal.style.top = "0px";

    requestAnimationFrame(() => {
        const modalWidth = modal.offsetWidth;
        const modalHeight = modal.offsetHeight;
        modal.style.left = absoluteX - modalWidth / 2 + "px";
        modal.style.top = absoluteY - modalHeight - 10 + "px";
        document.getElementById("edit-text-input").focus();
    });

    document.getElementById("edit-text-input").value = textDiv.innerText;
    document.getElementById("edit-text-size").value = parseInt(textDiv.style.fontSize, 10);
    document.getElementById("edit-text-color").value = textDiv.style.color;
}

document.getElementById("cancel-edit-btn").addEventListener("click", () => {
    document.getElementById("edit-text-modal").style.display = "none";
    currentEditingText = null;
});

document.getElementById("remove-text-btn").addEventListener("click", () => {
    if (currentEditingText) currentEditingText.remove();
    document.getElementById("edit-text-modal").style.display = "none";
    currentEditingText = null;
});

document.getElementById("save-edit-btn").addEventListener("click", () => {
    if (currentEditingText) {
        currentEditingText.innerText = document.getElementById("edit-text-input").value;
        currentEditingText.style.fontSize = document.getElementById("edit-text-size").value + "px";
        currentEditingText.style.color = document.getElementById("edit-text-color").value;
    }
    document.getElementById("edit-text-modal").style.display = "none";
    currentEditingText = null;
});

function loadAnnotationsForPage(page) {
    document.querySelectorAll(".draggable-text").forEach((el) => {
        el.style.display = parseInt(el.dataset.page) === page ? "block" : "none";
    });
}
