const CategoryFilter = {
    categories: [],
    selectedCategories: new Set(),
    allDocuments: [],
    filteredDocuments: [],
    searchTerm: '',

    init() {
        this.container = document.getElementById('category-filters');
        this.activeSourcesList = document.getElementById('active-sources-list');
        this.searchInput = document.getElementById('doc-search-input');

        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => {
                this.searchTerm = e.target.value.trim().toLowerCase();
                this.applyFilter();
            });
        }

        this.loadCategories();
    },

    async loadCategories() {
        try {
            const data = await API.getDocuments();
            this.allDocuments = data.documents || [];
            const catSet = new Set(this.allDocuments.map(d => d.category));
            this.categories = Array.from(catSet);

            // ✅ Add all categories to selected set BEFORE rendering
            this.categories.forEach(cat => this.selectedCategories.add(cat));

            this.renderCategoryFilters();
            this.applyFilter();

            window.dispatchEvent(new Event('categoryFilterLoaded'));
        } catch (e) {
            console.error('Failed to load categories', e);
        }
    },

    renderCategoryFilters() {
        if (!this.container) return;
        this.container.innerHTML = '';
        const counts = {};
        this.allDocuments.forEach(doc => {
            counts[doc.category] = (counts[doc.category] || 0) + 1;
        });

        this.categories.forEach(cat => {
            const div = document.createElement('div');
            div.className = `category-filter-item ${this.selectedCategories.has(cat) ? 'selected' : ''}`;
            div.innerHTML = `
                <input type="checkbox" id="cat-${cat}" value="${cat}" ${this.selectedCategories.has(cat) ? 'checked' : ''}>
                <label for="cat-${cat}">${cat}</label>
                <span class="doc-count">${counts[cat] || 0}</span>
            `;
            const checkbox = div.querySelector('input');
            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedCategories.add(cat);
                } else {
                    this.selectedCategories.delete(cat);
                }
                div.classList.toggle('selected', e.target.checked);
                this.applyFilter();
            });
            this.container.appendChild(div);
        });
    },

    applyFilter() {
        // Filter by categories
        let docs = this.allDocuments;

        // Only apply category filter if at least one category is selected
        if (this.selectedCategories.size > 0) {
            docs = docs.filter(doc => this.selectedCategories.has(doc.category));
        }

        // Apply text search
        if (this.searchTerm) {
            docs = docs.filter(doc =>
                doc.name.toLowerCase().includes(this.searchTerm)
                // Add number search later: doc.number?.toLowerCase().includes(this.searchTerm)
            );
        }

        this.filteredDocuments = docs;
        this.renderActiveSources();

        // Notify Chat module to update its document tags and clear invalid selections
        if (typeof Chat !== 'undefined') {
            if (Chat.updateDocumentTags) {
                Chat.updateDocumentTags(this.filteredDocuments);
            }
            if (Chat.clearInvalidSelectedDocs) {
                Chat.clearInvalidSelectedDocs(this.filteredDocuments.map(d => d.name));
            }
        }
    },

    renderActiveSources() {
        if (!this.activeSourcesList) return;
        if (this.filteredDocuments.length === 0) {
            this.activeSourcesList.innerHTML = '<div class="kp-doc-item-small">No documents match</div>';
            return;
        }
        const html = this.filteredDocuments.map(doc =>
            `<div class="kp-doc-item-small" title="${doc.name}">📄 ${doc.name}</div>`
        ).join('');
        this.activeSourcesList.innerHTML = html;
    },

    getFilteredDocuments() {
        return this.filteredDocuments;
    }
};