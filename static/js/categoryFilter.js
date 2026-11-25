const CategoryFilter = {
    selectedCategories: new Set(),
    allDocuments: [],
    filteredDocuments: [],
    searchTerm: '',

    init() {
        this.container = document.getElementById('category-filters');
        this.activeSourcesList = document.getElementById('active-sources-list');
        this.status = document.getElementById('document-status');
        document.getElementById('doc-search-input').addEventListener('input', event => {
            this.searchTerm = event.target.value.trim().toLowerCase();
            this.applyFilter();
        });
        this.loadCategories();
    },

    setStatus(key, error = false) {
        if (key) this.status.dataset.i18n = key;
        else delete this.status.dataset.i18n;
        this.status.textContent = key ? I18N.t(key) : '';
        this.status.classList.toggle('error', error);
    },

    async loadCategories() {
        this.setStatus('chat_documents_loading');
        this.activeSourcesList.setAttribute('aria-busy', 'true');
        try {
            const data = await API.getDocuments();
            this.allDocuments = data.documents || [];
            this.selectedCategories = new Set(this.allDocuments.map(doc => doc.category));
            this.renderCategoryFilters();
            this.applyFilter();
        } catch (_) {
            this.setStatus('chat_documents_error', true);
        } finally {
            this.activeSourcesList.setAttribute('aria-busy', 'false');
        }
    },

    renderCategoryFilters() {
        this.container.replaceChildren();
        for (const category of this.selectedCategories) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'category-filter-item';
            button.dir = 'auto';
            button.textContent = category;
            button.setAttribute('aria-pressed', 'true');
            button.addEventListener('click', () => {
                if (!this.selectedCategories.delete(category)) this.selectedCategories.add(category);
                button.setAttribute('aria-pressed', String(this.selectedCategories.has(category)));
                this.applyFilter();
            });
            this.container.appendChild(button);
        }
    },

    applyFilter() {
        this.filteredDocuments = this.allDocuments.filter(doc =>
            (!this.selectedCategories.size || this.selectedCategories.has(doc.category)) &&
            doc.name.toLowerCase().includes(this.searchTerm)
        );
        Chat.clearInvalidSelectedDocs(this.filteredDocuments.map(doc => doc.name));
        this.renderActiveSources();
        if (this.status) this.setStatus(this.filteredDocuments.length ? '' : 'chat_no_documents');
    },

    renderActiveSources() {
        if (!this.activeSourcesList) return;
        this.activeSourcesList.replaceChildren();
        for (const doc of this.filteredDocuments) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'doc-row';
            button.dataset.document = doc.name;
            button.innerHTML = Chat.icon('documents');
            const labels = document.createElement('span');
            labels.className = 'doc-row__labels';
            const name = document.createElement('bdi');
            name.className = 'doc-row__name';
            name.dir = 'auto';
            name.textContent = doc.name;
            const category = document.createElement('bdi');
            category.className = 'doc-row__category';
            category.dir = 'auto';
            category.textContent = doc.category;
            labels.appendChild(name);
            labels.appendChild(category);
            button.appendChild(labels);
            button.setAttribute('aria-pressed', String(Chat.selectedDocs.includes(doc.name)));
            button.addEventListener('click', () => {
                if (!Chat.toggleDocument(doc, this.allDocuments)) return;
                button.setAttribute('aria-pressed', String(Chat.selectedDocs.includes(doc.name)));
                if (this.status) this.setStatus('');
            });
            this.activeSourcesList.appendChild(button);
        }
    },
};
