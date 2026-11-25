// static/js/kb_manager.js
document.addEventListener('DOMContentLoaded', () => {
    const canWrite = document.body.dataset.canWrite === 'true';
    let activeDocId = null;
    let activeDocTitle = "";
    let chunkLoad = 0;
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
            mainCategory: document.getElementById('new-chunk-main-category'),
            subCategory: document.getElementById('new-chunk-sub-category'),
            changedBy: document.getElementById('new-chunk-operator-name')
        }
    };

    loadAvailableDocuments();

    function apiErrorMessage(data, fallback) {
        if (typeof data?.detail === 'string') return data.detail;
        if (typeof data?.detail?.message === 'string') {
            const updateId = data.detail.knowledge_update_id;
            return updateId
                ? `${data.detail.message} (شناسه پیگیری: ${updateId})`
                : data.detail.message;
        }
        if (Array.isArray(data?.detail)) return data.detail.map(item => item.msg).join('؛ ');
        return fallback;
    }

    function validateTaxonomy(main, sub, focusTarget) {
        if (sub && !main) {
            displayToastNotify('برای زیردسته، ابتدا دسته‌بندی را وارد کنید.', 'error');
            focusTarget.focus();
            return false;
        }
        if ([main, sub].some(value => /[\r\n]|question\s+category\s*:|sub\s*_\s*category\s*:/i.test(value))) {
            displayToastNotify('فقط نام دسته‌بندی و زیردسته را در فیلدهای مربوط وارد کنید.', 'error');
            focusTarget.focus();
            return false;
        }
        return true;
    }

    function taxonomyControls(chunk) {
        return `<div class="kb-taxonomy-fields" aria-describedby="taxonomy-help-${chunk.id}">
            <div><label for="main-category-${chunk.id}">دسته‌بندی</label><input id="main-category-${chunk.id}" type="text" dir="auto" value="${escapeHTML(chunk.main_category || '')}" aria-describedby="taxonomy-help-${chunk.id}"></div>
            <div><label for="sub-category-${chunk.id}">زیردسته</label><input id="sub-category-${chunk.id}" type="text" dir="auto" value="${escapeHTML(chunk.sub_category || '')}" aria-describedby="taxonomy-help-${chunk.id}"></div>
            <p id="taxonomy-help-${chunk.id}" class="kb-taxonomy-help">اختیاری؛ با تغییر یا پاک‌کردن دسته‌بندی، زیردسته را دوباره مشخص کنید.</p>
            ${chunk.taxonomy_error ? '<p class="kb-taxonomy-error" role="alert">دسته‌بندی مبهم است؛ محتوای منبع باید پیش از ذخیره بررسی شود.</p>' : ''}
        </div>`;
    }

    // Event Bindings
    UI.searchBtn.addEventListener('click', () => triggerWorkspaceResetQuery());
    UI.searchBar.addEventListener('keyup', (e) => {
        if (e.key === 'Enter') triggerWorkspaceResetQuery();
    });

    UI.closeHistoryBtn.addEventListener('click', () => {
        UI.historyModal.close();
    });

    if (canWrite) {
        UI.closeAddModalBtn.addEventListener('click', () => {
            UI.addChunkModal.close();
        });

        UI.addChunkForm.isQa.addEventListener('change', (e) => {
            UI.addChunkForm.qaWrapper.classList.toggle('hidden', e.target.value !== 'true');
        });

        UI.saveNewChunkBtn.addEventListener('click', () => commitNewChunkToPipeline());
        UI.addChunkForm.mainCategory.addEventListener('input', () => { UI.addChunkForm.subCategory.value = ''; });
    }

    async function loadAvailableDocuments() {
        try {
            const res = await fetch('/knowledge-base/api/documents');
            if (!res.ok) throw new Error();
            const data = await res.json();
            renderSidebarNodes(data.documents);
        } catch (err) {
            UI.sidebar.innerHTML = '<p class="kb-message kb-message--error" dir="rtl">بارگیری اسناد انجام نشد. صفحه را تازه‌سازی کنید.</p>';
        } finally {
            UI.sidebar.setAttribute('aria-busy', 'false');
        }
    }

    function renderSidebarNodes(documents) {
        UI.sidebar.innerHTML = '';
        if (!documents || documents.length === 0) {
            UI.sidebar.innerHTML = '<p class="kb-message" dir="rtl">هیچ سندی یافت نشد.</p>';
            return;
        }

        documents.forEach(doc => {
            const button = document.createElement('button');
            button.className = 'sidebar-doc-node';
            button.type = 'button';
            button.setAttribute('aria-pressed', 'false');
            button.innerHTML = `<bdi>${escapeHTML(doc.title)}</bdi><svg aria-hidden="true"><use href="${document.body.dataset.iconsUrl}#documents"></use></svg>`;

            button.addEventListener('click', () => {
                document.querySelectorAll('.sidebar-doc-node').forEach(el => {
                    el.classList.toggle('is-active', el === button);
                    el.setAttribute('aria-pressed', String(el === button));
                });
                activeDocId = doc.id;
                activeDocTitle = doc.title;
                UI.searchBar.disabled = false;
                UI.searchBtn.disabled = false;
                button.dispatchEvent(new Event('workspace-document-selected', {bubbles: true}));

                currentOffset = 0;
                UI.searchBar.value = '';
                UI.workspace.innerHTML = '';

                renderDocumentHeading();
                fetchAndAppendChunks(doc.id, true);
            });
            UI.sidebar.appendChild(button);
        });
    }

    function renderDocumentHeading() {
        const actionRow = document.createElement('div');
        actionRow.className = 'kb-action-row workspace-surface';
        actionRow.innerHTML = `
            <div><h2 dir="auto">${escapeHTML(activeDocTitle)}</h2>${canWrite ? '' : '<p>فقط خواندنی</p>'}</div>
            ${canWrite ? '<button id="global-add-chunk-trigger" class="kb-write-action workspace-primary" type="button">افزودن تکه</button>' : ''}
        `;
        UI.workspace.appendChild(actionRow);

        if (canWrite) document.getElementById('global-add-chunk-trigger').addEventListener('click', () => {
            UI.addChunkForm.question.value = '';
            UI.addChunkForm.answer.value = '';
            UI.addChunkForm.mainCategory.value = '';
            UI.addChunkForm.subCategory.value = '';
            UI.addChunkModal.querySelector('.kb-dialog-notice').hidden = true;
            UI.addChunkModal.showModal();
        });
    }

    function triggerWorkspaceResetQuery() {
        if (activeDocId) {
            currentOffset = 0;
            UI.workspace.innerHTML = '';
            renderDocumentHeading();
            fetchAndAppendChunks(activeDocId, true);
        }
    }

    async function fetchAndAppendChunks(docId, isFirstBatch = false) {
        if (isLoadLocked && !isFirstBatch) return;
        const loadId = ++chunkLoad;
        isLoadLocked = true;

        removeLoadMoreButtonElement();
        const loadIndicator = document.createElement('div');
        loadIndicator.id = "kb-loading-indicator";
        loadIndicator.className = 'kb-message';
        loadIndicator.setAttribute('role', 'status');
        loadIndicator.textContent = 'در حال بارگیری تکه‌ها…';
        UI.workspace.appendChild(loadIndicator);

        try {
            let endpoint = `/knowledge-base/api/chunks/${docId}?limit=${BATCH_LIMIT}&offset=${currentOffset}`;
            const searchVal = UI.searchBar.value.trim();
            if (searchVal !== '') {
                endpoint += `&search=${encodeURIComponent(searchVal)}`;
            }

            const res = await fetch(endpoint);
            const data = await res.json();
            if (loadId !== chunkLoad) return;
            loadIndicator.remove();
            if (!res.ok) throw new Error();

            if (isFirstBatch && (!data.chunks || data.chunks.length === 0)) {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = 'kb-message';
                emptyMsg.textContent = 'هیچ موجودیتی منطبق با فیلتر جستجو یافت نشد.';
                UI.workspace.appendChild(emptyMsg);
                return;
            }

            appendChunksToGrid(data.chunks);
            currentOffset += BATCH_LIMIT;

            if (data.has_more) {
                renderLoadMoreRow(docId);
            }

        } catch (err) {
            if (loadId === chunkLoad) {
                loadIndicator.remove();
                displayToastNotify('بارگیری تکه‌ها انجام نشد. دوباره تلاش کنید.', 'error');
            }
        } finally {
            if (loadId === chunkLoad) isLoadLocked = false;
        }
    }

    function appendChunksToGrid(chunks) {
        chunks.forEach(chunk => {
            const card = document.createElement('div');
            card.id = `chunk-card-wrapper-${chunk.id}`;
            card.className = 'kb-chunk workspace-surface';

            let dynamicBodyLayout = '';
            if (!canWrite) {
                dynamicBodyLayout = chunk.is_qa ? `
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div><span class="kb-field-label">سوال</span><div class="kb-readable-content question-readonly-panel" dir="auto">${escapeHTML(chunk.question)}</div></div>
                        <div><span class="kb-field-label">پاسخ</span><div class="kb-readable-content" dir="auto">${escapeHTML(chunk.answer)}</div></div>
                    </div>` : `<div><span class="kb-field-label">متن تکه</span><div class="kb-readable-content" dir="auto">${escapeHTML(chunk.answer)}</div></div>`;
            } else if (chunk.is_qa) {
                dynamicBodyLayout = `
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <span class="kb-field-label">پرسش (فقط خواندنی)</span>
                            <div class="kb-readable-content question-readonly-panel" dir="auto">${escapeHTML(chunk.question)}</div>
                        </div>
                        <div>
                            <label for="target-field-${chunk.id}" class="kb-field-label">پاسخ</label>
                            <textarea id="target-field-${chunk.id}" class="kb-input kb-input--text" dir="auto">${escapeHTML(chunk.answer)}</textarea>
                        </div>
                    </div>
                `;
            } else {
                dynamicBodyLayout = `
                    <div>
                        <label for="target-field-${chunk.id}" class="kb-field-label">متن تکه</label>
                        <textarea id="target-field-${chunk.id}" class="kb-input kb-input--text" dir="auto">${escapeHTML(chunk.answer)}</textarea>
                    </div>
                `;
            }

            if (chunk.is_qa) {
                dynamicBodyLayout += canWrite ? taxonomyControls(chunk) : `<div class="kb-taxonomy-summary" dir="auto">دسته‌بندی: ${escapeHTML(chunk.main_category || 'ثبت نشده')}؛ زیردسته: ${escapeHTML(chunk.sub_category || 'ثبت نشده')}</div>`;
            }
            card.innerHTML = `
                <div class="kb-chunk-head">
                    <div class="kb-chunk-meta">
                        <strong>تکه ${chunk.chunk_index}</strong>
                        <span>شناسه <bdi>${escapeHTML(String(chunk.id))}</bdi></span>
                    </div>
                    <div class="kb-chunk-actions">
                        <button type="button" id="history-btn-${chunk.id}" class="workspace-secondary">
                            تاریخچه
                        </button>
                        ${canWrite ? `<button id="delete-btn-${chunk.id}" class="kb-write-action workspace-secondary kb-danger">
                            حذف
                        </button>
                        <button id="sync-btn-${chunk.id}" class="kb-write-action workspace-primary">
                            ذخیره تکه
                        </button>` : ''}
                    </div>
                </div>
                ${dynamicBodyLayout}
                ${canWrite ? `<div class="kb-chunk-footer">
                    <label for="operator-field-${chunk.id}">شناسه اپراتور</label>
                    <input type="text" id="operator-field-${chunk.id}" value="Hooman (AI Engineer)" class="kb-input" dir="auto" />
                </div>` : ''}
            `;

            UI.workspace.appendChild(card);

            if (canWrite) document.getElementById(`sync-btn-${chunk.id}`).addEventListener('click', (e) => executeAtomicPipelineSync(chunk, e.target));
            if (canWrite && chunk.is_qa) {
                const mainInput = document.getElementById(`main-category-${chunk.id}`);
                const subInput = document.getElementById(`sub-category-${chunk.id}`);
                mainInput.addEventListener('input', () => { subInput.value = ''; });
                if (chunk.taxonomy_error) document.getElementById(`sync-btn-${chunk.id}`).disabled = true;
            }
            document.getElementById(`history-btn-${chunk.id}`).addEventListener('click', () => launchHistoryTrackingModal(chunk.id));
            if (canWrite) document.getElementById(`delete-btn-${chunk.id}`).addEventListener('click', () => dispatchDeleteExecutionPipeline(chunk.id));
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
        const main = UI.addChunkForm.mainCategory.value.trim();
        const sub = UI.addChunkForm.subCategory.value.trim();
        if (isQa && !questionVal) {
            displayToastNotify('متن سوال را وارد کنید.', 'error');
            UI.addChunkForm.question.focus();
            return;
        }
        if (isQa && !validateTaxonomy(main, sub, UI.addChunkForm.mainCategory)) return;

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
                    changed_by: operator,
                    ...(isQa && main ? { main_category: main } : {}),
                    ...(isQa && sub ? { sub_category: sub } : {})
                })
            });

            const data = await response.json();
            if (response.ok) {
                UI.addChunkModal.close();
                displayToastNotify("تکه ذخیره شد.", "success");
                triggerWorkspaceResetQuery();
            } else {
                throw new Error(apiErrorMessage(data, "Error injecting item."));
            }
        } catch (err) {
            displayToastNotify(`خطا: ${err.message}`, "error");
        } finally {
            UI.saveNewChunkBtn.disabled = false;
            UI.saveNewChunkBtn.innerHTML = "ذخیره تکه";
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
                throw new Error(apiErrorMessage(result, "Purge pipeline issue."));
            }
        } catch (err) {
            displayToastNotify(`خطای ناموفقیت امیز: ${err.message}`, "error");
        }
    }

    async function launchHistoryTrackingModal(chunkId) {
        dynamicCurrentChunkIdForModal = chunkId;
        UI.historyList.innerHTML = `<div class="kb-message">در حال بازیابی تاریخچه نسخ ثبت شده...</div>`;
        UI.historyModal.querySelector('.kb-dialog-notice').hidden = true;
        UI.historyModal.showModal();

        try {
            const res = await fetch(`/knowledge-base/api/chunks/${chunkId}/versions`);
            const data = await res.json();
            renderHistoryVersionRows(data.versions);
        } catch (err) {
            UI.historyList.innerHTML = `<div class="kb-message kb-message--error">خطا در بارگذاری تاریخچه دیتابیس.</div>`;
        }
    }

    function renderHistoryVersionRows(versions) {
        UI.historyList.innerHTML = '';
        if (!versions || versions.length === 0) {
            UI.historyList.innerHTML = `<div class="kb-message">هیچ نسخه قدیمی تری برای این چانک یافت نشد.</div>`;
            return;
        }

        versions.forEach((ver, index) => {
            const row = document.createElement('div');
            row.className = 'kb-version';

            const textSnippet = ver.is_qa
                ? `<strong>سوال:</strong> ${escapeHTML(ver.question)}<br><strong>پاسخ:</strong> ${escapeHTML(ver.answer)}<br><strong>دسته‌بندی:</strong> ${escapeHTML(ver.main_category || 'ثبت نشده')}؛ <strong>زیردسته:</strong> ${escapeHTML(ver.sub_category || 'ثبت نشده')}`
                : escapeHTML(ver.answer);
            const dateParsed = new Date(ver.created_at).toLocaleString('fa-IR');

            row.innerHTML = `
                <div class="flex-1 text-right">
                    <div class="kb-version-head">
                        <span class="kb-version-index">نسخه #${versions.length - index}</span>
                        <span dir="auto">توسط: ${escapeHTML(ver.changed_by)}</span>
                        <span dir="ltr">${dateParsed}</span>
                    </div>
                    <div class="kb-readable-content" dir="auto">${textSnippet}</div>
                </div>
                ${canWrite ? `<button id="revert-btn-${ver.id}" class="kb-write-action workspace-secondary">
                    بازگردانی این نسخه
                </button>` : ''}
            `;
            UI.historyList.appendChild(row);

            if (canWrite) document.getElementById(`revert-btn-${ver.id}`).addEventListener('click', () => executeStateReversion(ver.id));
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
                UI.historyModal.close();
                displayToastNotify("نسخه بازگردانی شد.", "success");
                triggerWorkspaceResetQuery(); // Refresh tracking workspace grid nodes
            } else {
                throw new Error(apiErrorMessage(result, "Reversion pipeline execution error."));
            }
        } catch (err) {
            displayToastNotify(`خطا در بازگردانی: ${err.message}`, "error");
        }
    }

    function renderLoadMoreRow(docId) {
        const btnRow = document.createElement('button');
        btnRow.id = "kb-load-more-row-btn";
        btnRow.className = "workspace-secondary kb-more";
        btnRow.textContent = 'نمایش تکه‌های بیشتر';
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
        const taxonomy = {};
        if (chunk.is_qa) {
            if (chunk.taxonomy_error) {
                displayToastNotify('دسته‌بندی مبهم است؛ محتوای منبع باید بررسی شود.', 'error');
                return;
            }
            const mainInput = document.getElementById(`main-category-${chunk.id}`);
            const subInput = document.getElementById(`sub-category-${chunk.id}`);
            const main = mainInput.value.trim();
            const sub = subInput.value.trim();
            // Unchanged metadata is omitted so stale form values cannot undo a
            // concurrent taxonomy update when only the answer is edited.
            if (main !== (chunk.main_category || '')) taxonomy.main_category = main || null;
            if (sub !== (chunk.sub_category || '')) taxonomy.sub_category = sub || null;
            if (Object.keys(taxonomy).length && !validateTaxonomy(main, sub, mainInput)) return;
        }

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
                    changed_by: operatorName,
                    ...taxonomy
                })
            });

            const result = await response.json();
            if (response.ok) {
                if (typeof result.answer === 'string') {
                    inputArea.value = result.answer;
                    Object.assign(chunk, { answer: result.answer, main_category: result.main_category,
                        sub_category: result.sub_category, taxonomy_error: result.taxonomy_error });
                    if (chunk.is_qa) {
                        document.getElementById(`main-category-${chunk.id}`).value = result.main_category || '';
                        document.getElementById(`sub-category-${chunk.id}`).value = result.sub_category || '';
                    }
                }
                displayToastNotify(result.no_op ? 'تغییری برای ثبت وجود نداشت.' : "بروزرسانی موفقیت‌آمیز در پایگاه داده و Qdrant اعمال گردید.", "success");
            } else {
                throw new Error(apiErrorMessage(result, "Error processing pipeline script."));
            }
        } catch (err) {
            displayToastNotify(`خطا در پردازش: ${err.message}`, "error");
        } finally {
            buttonInstance.disabled = false;
            buttonInstance.innerHTML = originalHTML;
        }
    }

    let noticeNumber = 0;
    function displayToastNotify(message, mode) {
        const modal = [UI.addChunkModal, UI.historyModal].find(dialog => dialog?.open);
        const inline = modal?.querySelector('.kb-dialog-notice');
        const notice = inline || UI.toast;
        const text = inline || UI.toastText;
        const id = ++noticeNumber;
        text.textContent = message;
        notice.dataset.error = String(mode === 'error');
        notice.hidden = false;
        setTimeout(() => {
            if (id === noticeNumber) notice.hidden = true;
        }, 3500);
    }

    function escapeHTML(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
});
