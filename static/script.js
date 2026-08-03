const token = localStorage.getItem("auth_token")

if (!token) {

window.location.href = "/"

}

let currentSession = null

async function loadSessions() {

    const response = await fetch("/api/sessions",
    {

        headers: {"Authorization":
            "Bearer " + token
        }

    }
)

    const data = await response.json()

    const list = document.getElementById("sessionList")

    list.innerHTML = ""

data.sessions.forEach(s => {

    const div = document.createElement("div")

    div.className = "session - item"

div.innerText = s.name

    div.onclick = () => openSession(s.id)

    list.appendChild(div)

})

}


function addMessage(role, text) {

    const container = document.getElementById("chatMessages")

    const bubble = document.createElement("div")

    bubble.className = role === "user" ? "msg - user" : "msg - assistant"

    bubble.innerText = text

    container.appendChild(bubble)

    container.scrollTop = container.scrollHeight

}




let availableDocuments = [];
let selectedDocuments = new Set();
let selectedOCRFile = null;
let lastOCRResult = null;

// Initialize event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Update alpha value display
    const alphaInput = document.getElementById('alpha');
    if (alphaInput) {
        alphaInput.addEventListener('input', function() {
            document.getElementById('alphaValue').textContent = this.value;
        });
    }

    // Setup file upload area
    setupFileUpload();

    // Check OCR status on page load
    checkOCRStatus();
});

// ============== FILE UPLOAD SETUP ==============

function setupFileUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('ocrFile');

    if (!uploadArea || !fileInput) return;

    // Click to select file
    uploadArea.addEventListener('click', function(e) {
        if (e.target !== fileInput) {
            fileInput.click();
        }
    });

    // File input change
    fileInput.addEventListener('change', function(e) {
        if (e.target.files && e.target.files.length > 0) {
            selectFile(e.target.files[0]);
        }
    });

    // Drag and drop events
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.add('drag-over');
    });

    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');
    });

    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');

        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            selectFile(e.dataTransfer.files[0]);
        }
    });
}

// ============== TAB NAVIGATION ==============

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Find and activate the clicked button
    const clickedBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (clickedBtn) {
        clickedBtn.classList.add('active');
    }

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    if (tabName === 'rag') {
        document.getElementById('ragTab').classList.add('active');
    } else if (tabName === 'ocr') {
        document.getElementById('ocrTab').classList.add('active');
        checkOCRStatus();
    }
}

// ============== RAG SYSTEM FUNCTIONS ==============

async function initializeSystem() {
    const directoryPath = document.getElementById('directoryPath').value;
    const statusDiv = document.getElementById('initStatus');
    const loadingSpinner = document.getElementById('loadingSpinner');

    if (!directoryPath) {
        showStatus(statusDiv, 'لطفاً مسیر پوشه را وارد کنید', 'error');
        return;
    }

    showLoading('در حال راه‌اندازی سیستم...');
    statusDiv.innerHTML = '';

    try {
        const response = await fetch('/api/initialize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': "Bearer " + token
            },
            body: JSON.stringify({ directory_path: directoryPath })
        });

        const data = await response.json();

        if (response.ok) {
            availableDocuments = data.documents;
            showStatus(statusDiv, `✅ ${data.message} (${data.total_chunks} قطعه متن)`, 'success');
            displayDocuments();
            document.getElementById('documentSection').style.display = 'block';
            document.getElementById('querySection').style.display = 'block';
        } else {
            showStatus(statusDiv, `❌ خطا: ${data.detail}`, 'error');
        }
    } catch (error) {
        showStatus(statusDiv, `❌ خطای ارتباط: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

function displayDocuments() {
    const documentList = document.getElementById('documentList');
    documentList.innerHTML = '';

    availableDocuments.forEach(doc => {
        const docItem = document.createElement('div');
        docItem.className = 'document-item';
        docItem.innerHTML = `
            <label>
                <input type="checkbox" value="${doc}" onchange="toggleDocument('${doc}', this)">
                ${doc}
            </label>
        `;
        documentList.appendChild(docItem);
    });
}

function toggleDocument(docName, checkbox) {
    const docItem = checkbox.closest('.document-item');

    if (checkbox.checked) {
        selectedDocuments.add(docName);
        docItem.classList.add('selected');
    } else {
        selectedDocuments.delete(docName);
        docItem.classList.remove('selected');
    }
}

function selectAllDocuments() {
    const checkboxes = document.querySelectorAll('.document-item input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = true;
        selectedDocuments.add(cb.value);
        cb.closest('.document-item').classList.add('selected');
    });
}

function deselectAllDocuments() {
    const checkboxes = document.querySelectorAll('.document-item input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = false;
        cb.closest('.document-item').classList.remove('selected');
    });
    selectedDocuments.clear();
}

async function submitQuery() {
    const query = document.getElementById('queryText').value;
    const topK = parseInt(document.getElementById('topK').value);
    const alpha = parseFloat(document.getElementById('alpha').value);

    if (!query.trim()) {
        alert('لطفاً سوال خود را وارد کنید');
        return;
    }

    showLoading('در حال پردازش سوال...');

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': "Bearer " + token
            },
            body: JSON.stringify({
                session_id: currentSession,
                query: query,
                documents: Array.from(selectedDocuments),
                top_k: topK,
                alpha: alpha
            })
        });

        const data = await response.json();

        if (response.ok) {
            addMessage('user', query);                     // <-- ADD THIS (chat bubble)
            addMessage('assistant', data.answer);           // <-- ADD THIS (chat bubble)
            displayResults(data);

        } else {
            alert(`خطا: ${data.detail}`);
        }
    } catch (error) {
        alert(`خطای ارتباط: ${error.message}`);
    } finally {
        hideLoading();
    }
}

function displayResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    const answerText = document.getElementById('answerText');
    const docsList = document.getElementById('docsList');

    resultsSection.style.display = 'block';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    answerText.textContent = data.answer || 'پاسخی یافت نشد';

    docsList.innerHTML = '';
    data.results.forEach(result => {
        const docItem = document.createElement('div');
        docItem.className = 'doc-item';
        docItem.innerHTML = `
            <div class="doc-header">
                <div class="doc-rank">رتبه ${result.rank}</div>
                <div class="doc-scores">
                    <span class="score-badge">امتیاز کلی: ${result.score}</span>
                    <span class="score-badge">BM25: ${result.bm25_score}</span>
                    <span class="score-badge">معنایی: ${result.semantic_score}</span>
                </div>
            </div>
            <div class="doc-content">${result.content}</div>
        `;
        docsList.appendChild(docItem);
    });
}

// ============== OCR FUNCTIONS ==============

async function checkOCRStatus() {
    try {
        const response = await fetch('/api/ocr/status');
        const data = await response.json();

        const ocrButton = document.getElementById('ocrButton');
        const statusDiv = document.getElementById('ocrStatus');

        if (!data.available) {
            showStatus(statusDiv, '⚠️ سرویس OCR در دسترس نیست.', 'error');
            if (ocrButton) {
                ocrButton.disabled = true;
            }
        } else {
            // Clear any previous error status
            if (statusDiv) {
                statusDiv.innerHTML = '';
            }
            if (ocrButton) {
                ocrButton.disabled = false;
            }
        }
    } catch (error) {
        console.error('Error checking OCR status:', error);
    }
}

function selectFile(file) {
    const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif', '.webp'];
    const fileName = file.name.toLowerCase();
    const fileExt = '.' + fileName.split('.').pop();

    if (!validExtensions.includes(fileExt)) {
        alert('فرمت فایل پشتیبانی نمی‌شود. لطفاً یک فایل PDF یا تصویر انتخاب کنید.');
        return;
    }

    selectedOCRFile = file;

    const fileNameSpan = document.getElementById('selectedFileName');
    const fileInfoDiv = document.getElementById('selectedFileInfo');
    const statusDiv = document.getElementById('ocrStatus');

    if (fileNameSpan) {
        fileNameSpan.textContent = `📄 ${file.name} (${formatFileSize(file.size)})`;
    }
    if (fileInfoDiv) {
        fileInfoDiv.style.display = 'flex';
    }
    if (statusDiv) {
        statusDiv.innerHTML = '';
    }

    // Hide previous results
    const resultsSection = document.getElementById('ocrResultsSection');
    if (resultsSection) {
        resultsSection.style.display = 'none';
    }

    console.log('File selected:', file.name, file.size, file.type);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function clearSelectedFile() {
    selectedOCRFile = null;

    const fileInput = document.getElementById('ocrFile');
    const fileInfoDiv = document.getElementById('selectedFileInfo');
    const resultsSection = document.getElementById('ocrResultsSection');
    const statusDiv = document.getElementById('ocrStatus');

    if (fileInput) {
        fileInput.value = '';
    }
    if (fileInfoDiv) {
        fileInfoDiv.style.display = 'none';
    }
    if (resultsSection) {
        resultsSection.style.display = 'none';
    }
    if (statusDiv) {
        statusDiv.innerHTML = '';
    }

    lastOCRResult = null;
}

async function performOCR() {
    if (!selectedOCRFile) {
        alert('لطفاً ابتدا یک فایل انتخاب کنید');
        return;
    }

    const statusDiv = document.getElementById('ocrStatus');

    showLoading('در حال استخراج متن... این عملیات ممکن است چند لحظه طول بکشد.');

    try {
        const formData = new FormData();
        formData.append('file', selectedOCRFile);

        console.log('Sending file for OCR:', selectedOCRFile.name);

        const response = await fetch('/api/ocr/extract', {
            method: 'POST',
            body: formData
        });

        console.log('Response status:', response.status);

        const data = await response.json();
        console.log('Response data:', data);

        if (response.ok) {
            lastOCRResult = data;
            displayOCRResults(data);
            showStatus(statusDiv, '✅ متن با موفقیت استخراج شد', 'success');
        } else {
            showStatus(statusDiv, `❌ خطا: ${data.detail}`, 'error');
        }
    } catch (error) {
        console.error('OCR Error:', error);
        showStatus(statusDiv, `❌ خطای ارتباط: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

function displayOCRResults(data) {
    const resultsSection = document.getElementById('ocrResultsSection');
    const statsDiv = document.getElementById('ocrStats');
    const textContainer = document.getElementById('ocrExtractedText');

    if (!resultsSection || !statsDiv || !textContainer) {
        console.error('OCR result elements not found');
        return;
    }

    // Show results section
    resultsSection.style.display = 'block';

    // Scroll to results
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }, 100);

    // Display statistics
    statsDiv.innerHTML = `
        <div class="stat-item">
            <span class="stat-label">📄 نام فایل:</span>
            <span class="stat-value">${data.filename}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">📁 نوع فایل:</span>
            <span class="stat-value">${data.file_type}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">📝 تعداد کلمات:</span>
            <span class="stat-value">${data.statistics.word_count.toLocaleString('fa-IR')}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">🔤 تعداد کاراکترها:</span>
            <span class="stat-value">${data.statistics.character_count.toLocaleString('fa-IR')}</span>
        </div>
    `;

    // Display extracted text
    if (data.extracted_text && data.extracted_text.trim()) {
        textContainer.textContent = data.extracted_text;
    } else {
        textContainer.textContent = 'متنی استخراج نشد. ممکن است تصویر حاوی متن نباشد یا کیفیت آن پایین باشد.';
    }
}

function copyOCRText() {
    if (lastOCRResult && lastOCRResult.extracted_text) {
        navigator.clipboard.writeText(lastOCRResult.extracted_text).then(() => {
            alert('✅ متن در کلیپ‌بورد کپی شد');
        }).catch(err => {
            console.error('Failed to copy text:', err);
            // Fallback method
            const textArea = document.createElement('textarea');
            textArea.value = lastOCRResult.extracted_text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            alert('✅ متن در کلیپ‌بورد کپی شد');
        });
    } else {
        alert('متنی برای کپی وجود ندارد');
    }
}

function downloadOCRText() {
    if (lastOCRResult && lastOCRResult.extracted_text) {
        const blob = new Blob([lastOCRResult.extracted_text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // Create filename from original file
        const originalName = lastOCRResult.filename.replace(/\.[^/.]+$/, '');
        a.download = `${originalName}_extracted.txt`;

        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } else {
        alert('متنی برای دانلود وجود ندارد');
    }
}

// ============== UTILITY FUNCTIONS ==============

function showStatus(element, message, type) {
    if (element) {
        element.innerHTML = `<div class="status-message ${type}">${message}</div>`;
    }
}

function showLoading(message = 'در حال پردازش...') {
    const spinner = document.getElementById('loadingSpinner');
    const loadingText = document.getElementById('loadingText');

    if (spinner) {
        spinner.style.display = 'flex';
    }
    if (loadingText) {
        loadingText.textContent = message;
    }
}

function hideLoading() {
    const spinner = document.getElementById('loadingSpinner');
    if (spinner) {
        spinner.style.display = 'none';
    }
}