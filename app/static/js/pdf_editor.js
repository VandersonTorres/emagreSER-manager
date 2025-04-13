let pdfDoc = null;
let scale = 1.5;
let canvas = document.getElementById('pdf-canvas');
let ctx = canvas.getContext('2d');
let currentEditingText = null;

pdfjsLib.getDocument(pdfUrl).promise.then(function (pdfDoc_) {
  pdfDoc = pdfDoc_;
  renderPage(1);
});

function renderPage(num) {
  pdfDoc.getPage(num).then(function(page) {
    let viewport = page.getViewport({scale: scale});
    canvas.height = viewport.height;
    canvas.width = viewport.width;
    page.render({
      canvasContext: ctx,
      viewport: viewport
    });
  });
}

canvas.addEventListener('click', function(event) {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    openTextModal(x, y);
});

function openTextModal(x, y) {
    let modal = document.getElementById('text-modal');
    let editModal = document.getElementById('edit-text-modal');
    let canvas = document.querySelector('canvas');
    let canvasRect = canvas.getBoundingClientRect();

    if (editModal.style.display === 'flex') {
        editModal.style.display = 'none';
    }

    let absoluteX = canvasRect.left + x;
    let absoluteY = canvasRect.top + y;

    modal.style.display = 'flex';

    modal.style.left = '0px';
    modal.style.top = '0px';
    modal.classList.add('show');

    const textInput = document.getElementById('text-input');
    textInput.value = '';

    requestAnimationFrame(() => {
        let modalWidth = modal.offsetWidth;
        let modalHeight = modal.offsetHeight;

        modal.style.left = (absoluteX - modalWidth / 2) + 'px';
        modal.style.top = (absoluteY - modalHeight - 10) + 'px';
        textInput.focus();
    });

    modal.dataset.x = x;
    modal.dataset.y = y;
}

document.getElementById('cancel-btn').addEventListener('click', function() {
    document.getElementById('text-modal').style.display = 'none';
});

document.getElementById('add-text-btn').addEventListener('click', function() {
    let modal = document.getElementById('text-modal');
    let text = document.getElementById('text-input').value;
    let size = document.getElementById('text-size').value;
    let color = document.getElementById('text-color').value;
    let x = modal.dataset.x;
    let y = modal.dataset.y;
    if(text.trim() !== "") {
        addTextToPDF(text, x, y, size, color);
    }
    modal.classList.remove('show');
    modal.style.display = 'none';
});

function addTextToPDF(text, x, y, size, color) {
    let textDiv = document.createElement('div');
    textDiv.classList.add('draggable-text');
    textDiv.innerText = text;
    textDiv.style.position = 'absolute';
    textDiv.style.left = x + 'px';
    textDiv.style.top = y + 'px';
    textDiv.style.fontSize = size + 'px';
    textDiv.style.color = color;
    makeDraggable(textDiv);

    textDiv.addEventListener('click', function(e) {
        e.stopPropagation();
        editOrRemoveText(textDiv);
    });

    document.getElementById('pdf-container').appendChild(textDiv);
}

function makeDraggable(el) {
    let offsetX, offsetY;
    el.addEventListener('mousedown', function(e) {
        offsetX = e.offsetX;
        offsetY = e.offsetY;
        function mouseMoveHandler(e) {
            let rect = canvas.getBoundingClientRect();
            el.style.left = (e.clientX - rect.left - offsetX) + 'px';
            el.style.top = (e.clientY - rect.top - offsetY) + 'px';
        }
        function mouseUpHandler() {
            document.removeEventListener('mousemove', mouseMoveHandler);
            document.removeEventListener('mouseup', mouseUpHandler);
        }
        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
    });
}

function getAnnotations() {
    const annotations = [];
    document.querySelectorAll('.draggable-text').forEach(el => {
        annotations.push({
            text: el.innerText,
            x: parseInt(el.style.left, 10),
            y: parseInt(el.style.top, 10),
            fontSize: parseInt(el.style.fontSize, 10),
            color: el.style.color,
            page: 0, // se for multipágina, você pode adaptar isso
        });
    });
    return annotations;
}

function getEditedPDFData() {
    let dataURL = canvas.toDataURL("application/pdf");
    return dataURL.split(',')[1];
}

async function savePDF() {
    const annotations = getAnnotations();

    const response = await fetch(window.location.href, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ annotations }),
    });

    try {
        const result = await response.json();

        if (result.status === "success") {
            alert(result.message);
            window.location.href = result.redirect_url;
        } else {
            alert(result.message || "Ocorreu um erro.");
        }
    } catch (e) {
        console.error("Erro ao tentar interpretar a resposta como JSON:", e);
    }
}

function editOrRemoveText(textDiv) {
    currentEditingText = textDiv;
    const modal = document.getElementById('edit-text-modal');
    const addModal = document.getElementById('text-modal');
    const canvasRect = canvas.getBoundingClientRect();
    const x = parseInt(textDiv.style.left, 10);
    const y = parseInt(textDiv.style.top, 10);

    if (addModal.style.display === 'flex') {
        addModal.style.display = 'none';
    }

    let absoluteX = canvasRect.left + x;
    let absoluteY = canvasRect.top + y;

    modal.style.display = 'flex';
    modal.style.left = '0px';
    modal.style.top = '0px';

    requestAnimationFrame(() => {
        const modalWidth = modal.offsetWidth;
        const modalHeight = modal.offsetHeight;
        modal.style.left = (absoluteX - modalWidth / 2) + 'px';
        modal.style.top = (absoluteY - modalHeight - 10) + 'px';
        document.getElementById('edit-text-input').focus();
    });

    document.getElementById('edit-text-input').value = textDiv.innerText;
    document.getElementById('edit-text-size').value = parseInt(textDiv.style.fontSize, 10);
    document.getElementById('edit-text-color').value = textDiv.style.color;
}

document.getElementById('cancel-edit-btn').addEventListener('click', () => {
    document.getElementById('edit-text-modal').style.display = 'none';
    currentEditingText = null;
});

document.getElementById('remove-text-btn').addEventListener('click', () => {
    if (currentEditingText) {
        currentEditingText.remove();
        currentEditingText = null;
    }
    document.getElementById('edit-text-modal').style.display = 'none';
});

document.getElementById('save-edit-btn').addEventListener('click', () => {
    if (currentEditingText) {
        currentEditingText.innerText = document.getElementById('edit-text-input').value;
        currentEditingText.style.fontSize = document.getElementById('edit-text-size').value + 'px';
        currentEditingText.style.color = document.getElementById('edit-text-color').value;
    }
    document.getElementById('edit-text-modal').style.display = 'none';
    currentEditingText = null;
});

document.getElementById("save-changes-btn").addEventListener("click", savePDF);
