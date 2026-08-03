const Sidebar = {
    selectedDocuments: [],

    async init() {
        await this.loadDocuments();
        this.bindEvents();
    },

    async loadDocuments() {
        const list = document.getElementById("doc-list");
        if (!list) return;

        list.innerHTML = `<li class="loading">Loading documents...</li>`;

        try {
            const data = await API.getDocuments();

            if (!data.documents || data.documents.length === 0) {
                list.innerHTML = `<li class="empty">No documents found. Initialize the system first.</li>`;
                return;
            }

            list.innerHTML = "";
            data.documents.forEach(docName => {
                const li = document.createElement("li");
                li.className = "doc-item";
                li.dataset.doc = docName;
                li.innerHTML = `
          <input type="checkbox" id="doc-${docName}" value="${docName}" />
          <label for="doc-${docName}">${docName}</label>
        `;

                li.querySelector("input").addEventListener("change", (e) => {
                    this.toggleDocument(docName, e.target.checked);
                });

                list.appendChild(li);
            });

        } catch (err) {
            list.innerHTML = `<li class="error">Failed to load documents.</li>`;
            console.error("Sidebar.loadDocuments error:", err);
        }
    },

    toggleDocument(docName, isChecked) {
        if (isChecked) {
            if (!this.selectedDocuments.includes(docName)) {
                this.selectedDocuments.push(docName);
            }
        } else {
            this.selectedDocuments = this.selectedDocuments.filter(d => d !== docName);
        }

        // Notify dashboard of selection change
        Dashboard.onDocumentSelectionChanged(this.selectedDocuments);
    },

    getSelectedDocuments() {
        return this.selectedDocuments;
    },

    async initializeSystem() {
        const dirInput = document.getElementById("dir-path");
        if (!dirInput) return;

        const directory = dirInput.value.trim();
        if (!directory) {
            alert("Please enter a directory path.");
            return;
        }

        const btn = document.getElementById("init-btn");
        if (btn) btn.disabled = true;

        try {
            const data = await API.initialize(directory);

            if (data.status === "success") {
                alert(`✅ Initialized: ${data.total_chunks} chunks from ${data.documents.length} documents.`);
                await this.loadDocuments();
            } else {
                alert("Initialization failed: " + (data.detail || "Unknown error"));
            }

        } catch (err) {
            alert("Error during initialization.");
            console.error("Sidebar.initializeSystem error:", err);
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    bindEvents() {
        const initBtn = document.getElementById("init-btn");
        if (initBtn) {
            initBtn.addEventListener("click", () => this.initializeSystem());
        }

        const refreshBtn = document.getElementById("refresh-docs-btn");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => this.loadDocuments());
        }
    },
};


const Sessions = {
    currentSessionId: null,
    createPromise: null,
    rawSessions: [],           // store unfiltered sessions
    currentFilter: "today",    // default filter

    // load from API, store, and apply filter
    async load() {
        try {
            const data = await API.getSessions();
            this.rawSessions = data.sessions || [];
            this.applyFilterAndRender();
        } catch (err) {
            console.error('Failed to load sessions:', err);
        }
    },

    // apply currentFilter to rawSessions and call render
    applyFilterAndRender() {
        const filtered = this.filterSessions(this.rawSessions, this.currentFilter);
        this.render(filtered);
    },

    // filter logic: pinned always first, then by date range
    // sidebar.js – Sessions.filterSessions
// sidebar.js – Sessions.filterSessions
    filterSessions(sessions, filter) {
        if (!sessions.length) return [];

        // Normalise is_pinned to boolean for every session
        const normalised = sessions.map(s => ({
            ...s,
            is_pinned: !!s.is_pinned,
        }));

        // Separate pinned and unpinned
        const pinned = normalised.filter(s => s.is_pinned);
        const unpinned = normalised.filter(s => !s.is_pinned);

        // Date helpers
        const now = new Date();
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterdayStart = new Date(todayStart);
        yesterdayStart.setDate(todayStart.getDate() - 1);
        const weekAgoStart = new Date(todayStart);
        weekAgoStart.setDate(todayStart.getDate() - 6);

        // Apply date filter ONLY to unpinned sessions
        const filteredUnpinned = unpinned.filter(s => {
            const lastActive = new Date(s.last_activity_at);
            switch (filter) {
                case "today":
                    return lastActive >= todayStart;
                case "yesterday":
                    return lastActive >= yesterdayStart && lastActive < todayStart;
                case "last7days":
                    return lastActive >= weekAgoStart && lastActive < yesterdayStart;
                case "older":
                    return lastActive < weekAgoStart;
                default:
                    return true; // "all" or undefined -> keep all
            }
        });

        // Sort each group: by last_activity_at DESC
        const sortDesc = (a, b) => new Date(b.last_activity_at) - new Date(a.last_activity_at);
        pinned.sort(sortDesc);
        filteredUnpinned.sort(sortDesc);

        // Pinned always appear first, then filtered unpinned
        return [...pinned, ...filteredUnpinned];
    },

    // render the filtered list (using I18N.t() for translatable labels)
    render(sessions) {
        const list = document.querySelector('.sidebar__chat-list');
        if (!list) return;

        if (!sessions || !Array.isArray(sessions)) {
            list.innerHTML = '<p class="sidebar__empty">No chats yet</p>';
            return;
        }

        if (sessions.length === 0) {
            list.innerHTML = '<p class="sidebar__empty">No chats match this filter</p>';
            return;
        }

        list.innerHTML = sessions.map(s => `
      <div class="sidebar__chat-item ${s.id === this.currentSessionId ? 'sidebar__chat-item--active' : ''}"
           data-id="${s.id}">
        <div class="sidebar__chat-item__icon">${s.is_pinned ? '📌' : '💬'}</div>
        <div class="sidebar__chat-item__content" onclick="Sessions.select('${s.id}')">
          <div class="sidebar__chat-item__title">${s.title || 'Untitled Chat'}</div>
          <div class="sidebar__chat-item__meta">
            <span>${this.formatTime(s.updated_at)}</span>
          </div>
        </div>
        <div class="sidebar__chat-item__actions">
          <button class="sidebar__chat-item__menu-btn" onclick="Sessions.toggleMenu(event, '${s.id}')">
            ⋮
          </button>
          <div class="sidebar__chat-item__menu" id="menu-${s.id}">
            <button class="sidebar__chat-item__menu-item" onclick="Sessions.pinSession(event, '${s.id}')">
              <span class="menu-icon">${s.is_pinned ? '📍' : '📌'}</span>
              <span>${s.is_pinned ? I18N.t('session_unpin') : I18N.t('session_pin')}</span>
            </button>
            <button class="sidebar__chat-item__menu-item" onclick="Sessions.downloadSession(event, '${s.id}')">
              <span class="menu-icon">⬇️</span>
              <span>${I18N.t('session_download')}</span>
            </button>
            <button class="sidebar__chat-item__menu-item sidebar__chat-item__menu-item--danger" onclick="Sessions.deleteSession(event, '${s.id}')">
              <span class="menu-icon">🗑️</span>
              <span>${I18N.t('session_delete')}</span>
            </button>
          </div>
        </div>
      </div>
    `).join('');
    },

    // Load messages for a session
    async loadMessages(sessionId) {
        const res = await fetch(`/api/sessions/${sessionId}/messages`);
        const data = await res.json();
        const messages = data.messages || data;
        const container = document.getElementById('messages');
        container.innerHTML = '';
        messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message message--${msg.role}`;
            div.textContent = msg.content;
            container.appendChild(div);
        });
    },

    // Create a new session
    async create() {
        if (this.createPromise) return this.createPromise;
        this.createPromise = (async () => {
            const res = await fetch('/api/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'New Chat'})
            });
            const session = await res.json();
            this.currentSessionId = parseInt(session.id);
            await this.load();          // refresh sidebar list (will re-apply filter)
            return session;
        })();
        const result = await this.createPromise;
        this.createPromise = null;
        return result;
    },

    async ensureSession() {
        if (this.currentSessionId) return this.currentSessionId;
        const session = await this.create();
        return session.id;
    },

    async select(sessionId) {
        this.currentSessionId = parseInt(sessionId);
        await this.load();            // re-render with active highlight
        try {
            const res = await fetch(`/api/sessions/${sessionId}/messages`);
            const data = await res.json();
            const messages = Array.isArray(data) ? data : (data.messages || []);
            Chat.loadMessages(messages);
        } catch (err) {
            console.error('Failed to load messages for session:', sessionId, err);
        }
    },

    formatTime(iso) {
        const date = new Date(iso);
        if (isNaN(date.getTime())) return 'نامشخص';

        const formatter = new Intl.DateTimeFormat('fa-IR', {
            timeZone: 'Asia/Tehran',
            calendar: 'persian',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        const fullPersianDate = formatter.format(date);
        const parts = formatter.formatToParts(date);
        const yearPart = parts.find(p => p.type === 'year');
        const year = yearPart ? yearPart.value : null;

        const now = new Date();
        const nowParts = formatter.formatToParts(now);
        const currentYear = nowParts.find(p => p.type === 'year')?.value;

        if (year === currentYear) {
            return fullPersianDate.replace(` ${year}`, '');
        } else {
            return fullPersianDate;
        }
    },

    toggleMenu(event, sessionId) {
        event.stopPropagation();
        const menu = document.getElementById(`menu-${sessionId}`);
        if (!menu) return;

        const isOpen = menu.classList.contains('sidebar__chat-item__menu--open');
        if (isOpen) {
            menu.classList.remove('sidebar__chat-item__menu--open');
            return;
        }

        const allMenus = document.querySelectorAll('.sidebar__chat-item__menu');
        allMenus.forEach(m => m.classList.remove('sidebar__chat-item__menu--open'));

        const button = event.currentTarget;
        const rect = button.getBoundingClientRect();
        const menuWidth = menu.offsetWidth;
        const menuHeight = menu.offsetHeight;
        const gap = 4;

        let top = rect.bottom + gap;
        let left = rect.right - menuWidth;

        if (top + menuHeight > window.innerHeight) {
            top = rect.top - menuHeight - gap;
        }
        if (left < 0) left = 8;
        if (left + menuWidth > window.innerWidth) {
            left = window.innerWidth - menuWidth - 8;
        }

        menu.style.top = `${top}px`;
        menu.style.left = `${left}px`;
        menu.classList.add('sidebar__chat-item__menu--open');
    },

    async deleteSession(event, sessionId) {
        event.stopPropagation();
        if (!confirm(I18N.t('session_delete_confirm'))) return;
        try {
            await API.deleteSession(sessionId);
            if (this.currentSessionId === sessionId) {
                this.currentSessionId = null;
                const chatMessages = document.querySelector('.chat__messages');
                if (chatMessages) chatMessages.innerHTML = '<p class="chat__empty">Select a chat or start a new one</p>';
            }
            await this.load();
        } catch (err) {
            console.error('Failed to delete session:', err);
            alert('Failed to delete chat. Please try again.');
        }
    },

    async pinSession(event, sessionId) {
        event.stopPropagation();
        try {
            const result = await API.pinSession(sessionId);
            if (result.success) await this.load();
        } catch (err) {
            console.error('Failed to pin session:', err);
            alert('Failed to pin chat. Please try again.');
        }
    },

    downloadSession(event, sessionId) {
        event.stopPropagation();
        // Close the dropdown menu
        const menu = document.getElementById(`menu-${sessionId}`);
        if (menu) menu.classList.remove('sidebar__chat-item__menu--open');

        fetch(`/api/sessions/${sessionId}/download`)
            .then(response => {
                if (!response.ok) throw new Error('Download failed');
                return response.blob();
            })
            .then(blob => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `session_${sessionId}.html`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
            })
            .catch(err => {
                console.error('Download error:', err);
                alert('Failed to download chat history.');
            });
    },

    // setup filter dropdown listener
    initFilter() {
        const filterSelect = document.getElementById('session-filter');
        const scrollContainer = document.querySelector('.sidebar__chat-scroll');
        if (scrollContainer) {
            scrollContainer.addEventListener('scroll', () => {
                document.querySelectorAll('.sidebar__chat-item__menu--open')
                    .forEach(m => m.classList.remove('sidebar__chat-item__menu--open'));
            });
        }
        if (filterSelect) {
            filterSelect.addEventListener('change', (e) => {
                this.currentFilter = e.target.value;
                this.applyFilterAndRender();
            });
        }
    },
};

// Initialize filter on page load
document.addEventListener('DOMContentLoaded', () => {
    Sessions.initFilter();
});

// Close menus when clicking outside
document.addEventListener('click', () => {
    const allMenus = document.querySelectorAll('.sidebar__chat-item__menu');
    allMenus.forEach(m => m.classList.remove('sidebar__chat-item__menu--open'));
});

// Hook new-chat button
document.querySelector('.btn-new-chat')?.addEventListener('click', () => Sessions.create());

// Initial session load
Sessions.load();

// Re-render session list when language changes (so menu labels update)
window.addEventListener('languagechange', () => {
    if (Sessions.rawSessions.length) {
        Sessions.applyFilterAndRender();
    }
});