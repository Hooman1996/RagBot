// static/js/kb_manager.js
document.addEventListener('DOMContentLoaded', () => {
    let activeDocId = null;
    let currentOffset = 0;
    const BATCH_LIMIT = 20;
    let isLoadLocked = false;
    let dynamicCurrentChunkIdForModal = null;

    const UI = {
        sidebar: document.getElementById('document-sidebar-list'),
        workspace: document.getElementById('chunks-workspace-wrapper'),
        searchBar: document.getElementById('kb-search-input'),
        searchBtn: document.getElementById('kb-search-trigger'),
        toast: document.getElementById('global-toast'),
        toastText: document.getElementById('toast-text'),

        // Modal Interfaces UI references
        historyModal: document.getElementById('history-modal-overlay'),
        historyList: document.getElementById('history-versions-stack'),
        closeHistoryBtn: document.getElementById('close-history-modal'),

        addChunkModal: document.getElementById('add-chunk-modal-overlay'),
        closeAddModalBtn: document.getElementById('close-add-modal'),
        saveNewChunkBtn: document.getElementById('submit-new-chunk-btn'),
        addChunkForm: {
            isQa: document.getElementById('new-chunk-is-qa'),
            qaWrapper: document.getElementById('new-chunk-qa-fields-wrapper'),
            question: document.getElementById('new-chunk-question'),
            answer: document.getElementById('new-chunk-answer'),
            changedBy: document.getElementById('new-chunk-operator-name')
        }
    };

    loadAvailableDocuments();

    // Event Bindings
    UI.searchBtn.addEventListener('click', () => triggerWorkspaceResetQuery());
    UI.searchBar.addEventListener('keyup', (e) => {
        if (e.key === 'Enter') triggerWorkspaceResetQuery();
    });

    UI.closeHistoryBtn.addEventListener('click', () => {
        UI.historyModal.classList.add('hidden');
        UI.historyModal.classList.remove('flex');
    });

    UI.closeAddModalBtn.addEventListener('click', () => {
        UI.addChunkModal.classList.add('hidden');
        UI.addChunkModal.classList.remove('flex');
    });

    UI.addChunkForm.isQa.addEventListener('change', (e) => {
        if (e.target.value === 'true') {
            UI.addChunkForm.qaWrapper.classList.remove('hidden');
        } else {
            UI.addChunkForm.qaWrapper.classList.add('hidden');
        }
    });

    UI.saveNewChunkBtn.addEventListener('click', () => commitNewChunkToPipeline());

    async function loadAvailableDocuments() {
        try {
            const res = await fetch('/knowledge-base/api/documents');
            const data = await res.json();
            renderSidebarNodes(data.documents);
        } catch (err) {
            UI.sidebar.innerHTML = `<div class="text-red-400 text-xs p-2">خطا در بارگذاری اطلاعات پیش آمد.</div>`;
        }
    }

    function renderSidebarNodes(documents) {
        UI.sidebar.innerHTML = '';
        if (!documents || documents.length === 0) {
            UI.sidebar.innerHTML = `<div class="text-slate-500 text-xs p-2">هیچ سندی یافت نشد.</div>`;
            return;
        }

        documents.forEach(doc => {
            const button = document.createElement('button');
            button.className = 'sidebar-doc-node w-full text-right text-xs px-3 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800/80 border border-slate-800 text-slate-300 transition-all truncate block';
            button.innerHTML = `📄 <span class="mr-1">${escapeHTML(doc.title)}</span>`;

            button.addEventListener('click', () => {
                document.querySelectorAll('.sidebar-doc-node').forEach(el => el.classList.remove('is-active'));
                button.classList.add('is-active');
                activeDocId = doc.id;

                currentOffset = 0;
                UI.searchBar.value = '';
                UI.workspace.innerHTML = '';

                injectActionActionBarHeaderRow();
                fetchAndAppendChunks(doc.id, true);
            });
            UI.sidebar.appendChild(button);
        });
    }

    function injectActionActionBarHeaderRow() {
        const actionRow = document.createElement('div');
        actionRow.className = 'flex justify-between items-center bg-slate-950/60 p-4 border border-slate-800 rounded-xl mb-4';
        actionRow.innerHTML = `
            <div class="text-xs font-semibold text-slate-400">عملیات جاری سند:</div>
            <button id="global-add-chunk-trigger" class="bg-blue-600 hover:bg-blue-500 active:scale-95 text-white text-xs font-bold px-4 py-2 rounded-lg transition-all flex items-center gap-1.5 shadow-md shadow-blue-600/10">
                ➕ افزودن تکه داده جدید به سند
            </button>
        `;
        UI.workspace.appendChild(actionRow);

        document.getElementById('global-add-chunk-trigger').addEventListener('click', () => {
            UI.addChunkForm.question.value = '';
            UI.addChunkForm.answer.value = '';
            UI.addChunkModal.classList.remove('hidden');
            UI.addChunkModal.classList.add('flex');
        });
    }

    function triggerWorkspaceResetQuery() {
        if (activeDocId) {
            currentOffset = 0;
            UI.workspace.innerHTML = '';
            injectActionActionBarHeaderRow();
            fetchAndAppendChunks(activeDocId, true);
        }
    }

    async function fetchAndAppendChunks(docId, isFirstBatch = false) {
        if (isLoadLocked) return;
        isLoadLocked = true;

        removeLoadMoreButtonElement();
        const loadIndicator = document.createElement('div');
        loadIndicator.id = "kb-loading-indicator";
        loadIndicator.className = 'text-center py-8 text-slate-400 text-xs animate-pulse';
        loadIndicator.textContent = 'در حال فراخوانی پایگاه داده برداری...';
        UI.workspace.appendChild(loadIndicator);

        try {
            let endpoint = `/knowledge-base/api/chunks/${docId}?limit=${BATCH_LIMIT}&offset=${currentOffset}`;
            const searchVal = UI.searchBar.value.trim();
            if (searchVal !== '') {
                endpoint += `&search=${encodeURIComponent(searchVal)}`;
            }

            const res = await fetch(endpoint);
            const data = await res.json();

            if (document.getElementById("kb-loading-indicator")) {
                document.getElementById("kb-loading-indicator").remove();
            }

            if (isFirstBatch && (!data.chunks || data.chunks.length === 0)) {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = 'text-center py-20 text-slate-500 text-xs';
                emptyMsg.textContent = 'هیچ موجودیتی منطبق با فیلتر جستجو یافت نشد.';
                UI.workspace.appendChild(emptyMsg);
                isLoadLocked = false;
                return;
            }

            appendChunksToGrid(data.chunks);
            currentOffset += BATCH_LIMIT;

            if (data.has_more) {
                renderLoadMoreRow(docId);
            }

        } catch (err) {
            if (document.getElementById("kb-loading-indicator")) {
                document.getElementById("kb-loading-indicator").remove();
            }
            displayToastNotify("بارگذاری ناموفق اطلاعات شبکه ای رخ داد.", "error");
        } finally {
            isLoadLocked = false;
        }
    }

    function appendChunksToGrid(chunks) {
        chunks.forEach(chunk => {
            const card = document.createElement('div');
            card.id = `chunk-card-wrapper-${chunk.id}`;
            card.className = 'bg-slate-950 p-5 rounded-xl border border-slate-800/80 shadow-md flex flex-col gap-4 mb-4 relative group';

            let dynamicBodyLayout = '';
            if (chunk.is_qa) {
                dynamicBodyLayout = `
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <span class="block text-[11px] font-bold text-slate-400 mb-1.5">🔒 متن سوال متصل (غیرقابل ویرایش جهت حفظ بافت بردار):</span>
                            <div class="question-readonly-panel p-3 rounded-lg border border-slate-800 text-xs text-slate-300 min-h-[110px] max-h-[150px] overflow-y-auto leading-relaxed text-right" style="direction: rtl;">
                                ${escapeHTML(chunk.question)}
                            </div>
                        </div>
                        <div>
                            <span class="block text-[11px] font-bold text-blue-400 mb-1.5">✍ پاسخ الحاقی (قابل ویرایش):</span>
                            <textarea id="target-field-${chunk.id}" class="w-full bg-slate-900 border border-blue-900/60 focus:border-blue-500 rounded-lg p-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none transition-all h-[110px] resize-none leading-relaxed text-right" style="direction: rtl;">${escapeHTML(chunk.answer)}</textarea>
                        </div>
                    </div>
                `;
            } else {
                dynamicBodyLayout = `
                    <div>
                        <span class="block text-[11px] font-bold text-amber-500 mb-1.5">📝 متن تکه خام مستندات (بدون ساختار FAQ):</span>
                        <textarea id="target-field-${chunk.id}" class="w-full bg-slate-900 border border-slate-800 focus:border-amber-500 rounded-lg p-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none transition-all h-[110px] resize-none leading-relaxed text-right" style="direction: rtl;">${escapeHTML(chunk.answer)}</textarea>
                    </div>
                `;
            }

            card.innerHTML = `
                <div class="flex justify-between items-center border-b border-slate-800/60 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-md text-[10px] font-mono tracking-wider text-slate-400">تکه شماره #${chunk.chunk_index}</span>
                        <span class="text-[10px] text-slate-600 font-mono">شناسه چانک: ${chunk.id}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <button id="history-btn-${chunk.id}" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1">
                            ⏳ تاریخچه نسخ
                        </button>
                        <button id="delete-btn-${chunk.id}" class="bg-red-950/40 hover:bg-red-600 border border-red-900 text-red-400 hover:text-white px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1">
                            🗑 حذف قطعی
                        </button>
                        <button id="sync-btn-${chunk.id}" class="bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-slate-950 font-bold px-4 py-1.5 rounded-lg text-xs transition-all shadow-lg shadow-emerald-600/10 flex items-center gap-1.5">
                            💾 همگام‌سازی برداری
                        </button>
                    </div>
                </div>
                ${dynamicBodyLayout}
                <div class="flex items-center gap-2 border-t border-slate-900 pt-2">
                    <span class="text-[10px] text-slate-500">تغییر دهنده نهایی:</span>
                    <input type="text" id="operator-field-${chunk.id}" value="Hooman (AI Engineer)" class="bg-slate-900 text-[10px] text-slate-300 px-2 py-0.5 rounded border border-slate-800 focus:outline-none focus:border-blue-500 w-44" />
                </div>
            `;

            UI.workspace.appendChild(card);

            document.getElementById(`sync-btn-${chunk.id}`).addEventListener('click', (e) => executeAtomicPipelineSync(chunk, e.target));
            document.getElementById(`history-btn-${chunk.id}`).addEventListener('click', () => launchHistoryTrackingModal(chunk.id));
            document.getElementById(`delete-btn-${chunk.id}`).addEventListener('click', () => dispatchDeleteExecutionPipeline(chunk.id));
        });
    }

    async function commitNewChunkToPipeline() {
        const answerVal = UI.addChunkForm.answer.value.trim();
        const questionVal = UI.addChunkForm.question.value.trim();
        const isQa = UI.addChunkForm.isQa.value === 'true';
        const operator = UI.addChunkForm.changedBy.value.trim() || "Hooman (AI Engineer)";

        if (!answerVal) {
            alert("پر کردن فیلد متن اصلی / پاسخ الزامیست.");
            return;
        }

        UI.saveNewChunkBtn.disabled = true;
        UI.saveNewChunkBtn.textContent = "در حال ایجاد چانک...";

        try {
            const response = await fetch('/knowledge-base/api/chunks/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    document_id: activeDocId,
                    is_qa: isQa,
                    question: isQa ? questionVal : null,
                    answer: answerVal,
                    changed_by: operator
                })
            });

            const data = await response.json();
            if (response.ok) {
                displayToastNotify("تکه داده جدید با موفقیت ایجاد و ایندکس برداری شد.", "success");
                UI.addChunkModal.classList.add('hidden');
                UI.addChunkModal.classList.remove('flex');
                triggerWorkspaceResetQuery();
            } else {
                throw new Error(data.detail || "Error injecting item.");
            }
        } catch (err) {
            displayToastNotify(`خطا: ${err.message}`, "error");
        } finally {
            UI.saveNewChunkBtn.disabled = false;
            UI.saveNewChunkBtn.innerHTML = "✓ ثبت و ایجاد چانک برداری جدید";
        }
    }

    async function dispatchDeleteExecutionPipeline(chunkId) {
        if (!confirm("آیا از حذف قطعی این تکه داده از پایگاه داده PostgreSQL و دیتابیس برداری Qdrant اطمینان کامل دارید؟ این عملیات غیرقابل بازگشت است.")) {
            return;
        }

        try {
            const response = await fetch(`/knowledge-base/api/chunks/delete/${chunkId}`, {
                method: 'DELETE'
            });
            const result = await response.json();

            if (response.ok) {
                displayToastNotify("موجودیت با موفقیت از تمامی لایه‌ها حذف گردید.", "success");
                const card = document.getElementById(`chunk-card-wrapper-${chunkId}`);
                if (card) card.remove();
            } else {
                throw new Error(result.detail || "Purge pipeline issue.");
            }
        } catch (err) {
            displayToastNotify(`خطای ناموفقیت امیز: ${err.message}`, "error");
        }
    }

    async function launchHistoryTrackingModal(chunkId) {
        dynamicCurrentChunkIdForModal = chunkId;
        UI.historyList.innerHTML = `<div class="text-center py-6 text-slate-400 text-xs animate-pulse">در حال بازیابی تاریخچه نسخ ثبت شده...</div>`;
        UI.historyModal.classList.remove('hidden');
        UI.historyModal.classList.add('flex');

        try {
            const res = await fetch(`/knowledge-base/api/chunks/${chunkId}/versions`);
            const data = await res.json();
            renderHistoryVersionRows(data.versions);
        } catch (err) {
            UI.historyList.innerHTML = `<div class="text-red-400 text-xs text-center">خطا در بارگذاری تاریخچه دیتابیس.</div>`;
        }
    }

    function renderHistoryVersionRows(versions) {
        UI.historyList.innerHTML = '';
        if (!versions || versions.length === 0) {
            UI.historyList.innerHTML = `<div class="text-slate-500 text-xs text-center py-4">هیچ نسخه قدیمی تری برای این چانک یافت نشد.</div>`;
            return;
        }

        versions.forEach((ver, index) => {
            const row = document.createElement('div');
            row.className = 'bg-slate-900 p-4 rounded-lg border border-slate-800 flex flex-col gap-2 justify-between items-start md:flex-row md:items-center transition-all hover:border-slate-700';

            let textSnippet = ver.is_qa ? `<strong>سوال:</strong> ${ver.question}<br><strong>پاسخ:</strong> ${ver.answer}` : ver.answer;
            const dateParsed = new Date(ver.created_at).toLocaleString('fa-IR');

            row.innerHTML = `
                <div class="flex-1 text-right">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="bg-blue-950 text-blue-400 font-mono text-[10px] px-2 py-0.5 rounded border border-blue-900">نسخه #${versions.length - index}</span>
                        <span class="text-[11px] text-slate-400 font-medium">توسط: ${escapeHTML(ver.changed_by)}</span>
                        <span class="text-[10px] text-slate-500" dir="ltr">${dateParsed}</span>
                    </div>
                    <div class="text-xs text-slate-300 bg-slate-950 p-2.5 rounded border border-slate-800 max-h-24 overflow-y-auto leading-relaxed">
                        ${textSnippet}
                    </div>
                </div>
                <button id="revert-btn-${ver.id}" class="bg-amber-600 hover:bg-amber-500 text-slate-950 text-xs font-bold px-3 py-1.5 rounded-md mt-2 md:mt-0 transition-all active:scale-95 whitespace-nowrap">
                    ◄ بازگردانی به این نسخه
                </button>
            `;
            UI.historyList.appendChild(row);

            document.getElementById(`revert-btn-${ver.id}`).addEventListener('click', () => executeStateReversion(ver.id));
        });
    }

    async function executeStateReversion(versionId) {
        if (!confirm("آیا از بازگردانی بافت چانک به این نسخه ساختاری مطمئن هستید؟ نسخه جدیدی بر این مبنا ثبت خواهد شد.")) return;

        try {
            const response = await fetch('/knowledge-base/api/chunks/revert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chunk_id: dynamicCurrentChunkIdForModal,
                    version_id: versionId,
                    changed_by: "Hooman (AI Engineer)"
                })
            });

            const result = await response.json();
            if (response.ok) {
                displayToastNotify("تکه با موفقیت به ساختار محتوایی نسخه هدف بازگردانی شد.", "success");
                UI.historyModal.classList.add('hidden');
                UI.historyModal.classList.remove('flex');
                triggerWorkspaceResetQuery(); // Refresh tracking workspace grid nodes
            } else {
                throw new Error(result.detail || "Reversion pipeline execution error.");
            }
        } catch (err) {
            displayToastNotify(`خطا در بازگردانی: ${err.message}`, "error");
        }
    }

    function renderLoadMoreRow(docId) {
        const btnRow = document.createElement('button');
        btnRow.id = "kb-load-more-row-btn";
        btnRow.className = "w-full py-4 my-2 border border-dashed border-slate-700 hover:border-blue-500 text-slate-400 hover:text-blue-400 text-xs font-semibold rounded-xl bg-slate-950/40 transition-all flex flex-col items-center justify-center gap-1 group";
        btnRow.innerHTML = `
            <span class="text-base group-hover:scale-110 transition-transform">•••</span>
            <span>مشاهده تکه‌های بیشتر این سند اطلاعاتی</span>
        `;
        btnRow.addEventListener('click', () => fetchAndAppendChunks(docId, false));
        UI.workspace.appendChild(btnRow);
    }

    function removeLoadMoreButtonElement() {
        const targetBtn = document.getElementById("kb-load-more-row-btn");
        if (targetBtn) targetBtn.remove();
    }

    async function executeAtomicPipelineSync(chunk, buttonInstance) {
        const inputArea = document.getElementById(`target-field-${chunk.id}`);
        const operatorName = document.getElementById(`operator-field-${chunk.id}`).value.trim() || "Hooman (AI Engineer)";
        const originalHTML = buttonInstance.innerHTML;

        buttonInstance.disabled = true;
        buttonInstance.innerHTML = `⏳ اعمال تغییرات...`;

        try {
            const response = await fetch('/knowledge-base/api/chunks/update', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chunk_id: chunk.id,
                    is_qa: chunk.is_qa,
                    question: chunk.question,
                    answer: inputArea.value,
                    changed_by: operatorName
                })
            });

            const result = await response.json();
            if (response.ok) {
                displayToastNotify("بروزرسانی موفقیت‌آمیز در پایگاه داده و Qdrant اعمال گردید.", "success");
            } else {
                throw new Error(result.detail || "Error processing pipeline script.");
            }
        } catch (err) {
            displayToastNotify(`خطا در پردازش: ${err.message}`, "error");
        } finally {
            buttonInstance.disabled = false;
            buttonInstance.innerHTML = originalHTML;
        }
    }

    function displayToastNotify(msg, mode) {
        UI.toastText.textContent = msg;
        if (mode === "success") {
            UI.toast.className = "fixed bottom-6 left-6 z-50 transform transition-all duration-300 bg-emerald-500 text-slate-950 font-bold text-xs px-5 py-3 rounded-lg shadow-xl shadow-emerald-500/10 flex items-center gap-2";
        } else {
            UI.toast.className = "fixed bottom-6 left-6 z-50 transform transition-all duration-300 bg-red-500 text-white font-bold text-xs px-5 py-3 rounded-lg shadow-xl shadow-red-500/10 flex items-center gap-2";
        }

        UI.toast.classList.remove('translate-y-12', 'opacity-0');
        setTimeout(() => {
            UI.toast.classList.add('translate-y-12', 'opacity-0');
        }, 4000);
    }

    function escapeHTML(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
});