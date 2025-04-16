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
