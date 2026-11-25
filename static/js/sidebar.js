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
            list.innerHTML = "";
            const error = document.createElement("li");
            error.className = "error";
            error.textContent = API.errorMessage(err);
            list.appendChild(error);
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
            alert(API.errorMessage(err));
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
    showError(error) {
        if (typeof Chat !== 'undefined') Chat.showError(error);
        else alert(API.errorMessage(error));
    },
    currentSessionId: null,
    createPromise: null,
    loadingMessages: null,
    rawSessions: [],           // store unfiltered sessions
    currentFilter: "today",    // default filter
    loadRequest: 0,

    // load from API, store, and apply filter
    async load() {
        const requestId = ++this.loadRequest;
        try {
            let data = await API.getSessions();
            if (!data.sessions || data.sessions.length === 0) {
                await API.createSession();
                data = await API.getSessions();
            }
            if (requestId !== this.loadRequest) return;
            this.rawSessions = data.sessions || [];
            this.loadFailed = false;
            this.applyFilterAndRender();
            this.updateThreadHeading();
        } catch (_) {
            if (requestId !== this.loadRequest) return;
            this.loadFailed = true;
            this.applyFilterAndRender();
        }
    },

    // apply currentFilter to rawSessions and call render
    applyFilterAndRender() {
        const filtered = this.filterSessions(this.rawSessions, this.currentFilter);
        this.render(filtered);
    },

    // filter logic: pinned always first, then by date range
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

    render(sessions) {
        const list = document.querySelector('.sidebar__chat-list');
        if (!list) return;
        const focused = document.activeElement?.closest('.sidebar__chat-item');
        const focusedMenu = document.activeElement?.classList.contains('sidebar__chat-item__menu-btn');
        this.closeMenu();
        list.replaceChildren();
        list.setAttribute('aria-busy', 'false');

        if (!sessions.length) {
            const empty = document.createElement('p');
            empty.className = 'sidebar__empty';
            empty.dir = 'auto';
            empty.dataset.i18n = this.loadFailed ? 'chat_history_error' : 'chat_no_history';
            empty.textContent = I18N.t(empty.dataset.i18n);
            list.appendChild(empty);
        }

        for (const session of sessions) {
            const id = Number(session.id);
            const active = id === this.currentSessionId;
            const row = document.createElement('div');
            row.className = 'sidebar__chat-item';
            row.classList.toggle('sidebar__chat-item--active', active);
            row.dataset.id = id;

            const open = document.createElement('button');
            open.type = 'button';
            open.className = 'sidebar__chat-item__content';
            if (active) open.setAttribute('aria-current', 'true');
            open.innerHTML = `<span class="sidebar__chat-item__icon">${Chat.icon(session.is_pinned ? 'pin' : 'chat')}</span>`;
            const label = document.createElement('bdi');
            label.className = 'sidebar__chat-item__title';
            this.setTitle(label, session.title);
            open.appendChild(label);
            open.addEventListener('click', () => {
                window.dispatchEvent(new Event('conversationselected'));
                this.select(id);
            });
            row.appendChild(open);

            const trigger = document.createElement('button');
            trigger.className = 'sidebar__chat-item__menu-btn';
            trigger.type = 'button';
            trigger.innerHTML = Chat.icon('more');
            trigger.setAttribute('aria-expanded', 'false');
            trigger.setAttribute('aria-controls', `menu-${id}`);
            trigger.dataset.i18nLabel = 'chat_session_actions';
            trigger.dataset.i18nTitle = 'chat_session_actions';
            trigger.title = I18N.t('chat_session_actions');
            trigger.setAttribute('aria-label', trigger.title);
            row.appendChild(trigger);

            const menu = document.createElement('div');
            menu.id = `menu-${id}`;
            menu.className = 'sidebar__chat-item__menu';
            menu.hidden = true;
            for (const [icon, labelKey, action] of [
                [session.is_pinned ? 'unpin' : 'pin', session.is_pinned ? 'session_unpin' : 'session_pin', this.pinSession],
                ['download', 'session_download', this.downloadSession],
                ['delete', 'session_delete', this.deleteSession],
            ]) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'sidebar__chat-item__menu-item';
                button.classList.toggle('sidebar__chat-item__menu-item--danger', icon === 'delete');
                button.innerHTML = `${Chat.icon(icon)}<span dir="auto" data-i18n="${labelKey}"></span>`;
                button.lastElementChild.textContent = I18N.t(labelKey);
                button.addEventListener('click', event => {
                    this.closeMenu(true);
                    action.call(this, event, id);
                });
                menu.appendChild(button);
            }
            row.appendChild(menu);
            trigger.addEventListener('click', () => this.toggleMenu(trigger, menu));
            list.appendChild(row);
        }

        if (focused && document.activeElement === document.body) {
            const currentRow = list.querySelector(`[data-id="${focused.dataset.id}"]`);
            const control = currentRow?.querySelector(focusedMenu ? '.sidebar__chat-item__menu-btn' : '.sidebar__chat-item__content');
            (control || document.querySelector('.btn-new-chat'))?.focus({preventScroll: true});
        }
    },

    setTitle(element, title) {
        if (title && title !== 'New Chat') {
            delete element.dataset.i18n;
            element.textContent = title;
        } else {
            element.dataset.i18n = 'chat_new_title';
            element.textContent = I18N.t('chat_new_title');
        }
        element.title = title && title !== 'New Chat' ? title : '';
    },

    updateThreadHeading() {
        const title = document.getElementById('thread-title');
        if (!title) return;
        const session = this.rawSessions.find(row => Number(row.id) === this.currentSessionId);
        this.setTitle(title, session?.title);
        const meta = document.getElementById('thread-meta');
        const date = new Date(session?.last_activity_at);
        meta.hidden = Number.isNaN(date.getTime());
        if (!meta.hidden) {
            const time = meta.querySelector('time');
            time.dateTime = date.toISOString();
            time.textContent = new Intl.DateTimeFormat(I18N.lang === 'fa' ? 'fa-IR' : 'en',
                { dateStyle: 'medium', timeStyle: 'short' }).format(date);
        }
    },

    activate(sessionId, loadingMessages = null, carryDraft = false) {
        const previousId = this.currentSessionId;
        this.currentSessionId = sessionId;
        this.loadingMessages = loadingMessages;
        if (previousId !== sessionId) {
            Chat.dictation?.cancel();
            Chat.sessionChanged(previousId, sessionId, carryDraft);
            if (loadingMessages) Chat.showLoading();
        }
        this.updateThreadHeading();
        if (Chat.sendBtn) Chat.setSendingState(Chat.isSending);
    },

    // Create a new session
    async create({onlyIfNone = false} = {}) {
        if (this.createPromise) return this.createPromise;
        Chat.dictation?.cancel();
        this.createPromise = (async () => {
            const res = await API.request('/api/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'New Chat'})
            });
            const session = await API.readJSON(res);
            if (!onlyIfNone || !this.currentSessionId) this.activate(Number(session.id), null, onlyIfNone);
            await this.load();          // refresh sidebar list (will re-apply filter)
            return session;
        })();
        try {
            return await this.createPromise;
        } finally {
            this.createPromise = null;
        }
    },

    async ensureSession() {
        if (this.currentSessionId) return this.currentSessionId;
        const session = await this.create({onlyIfNone: true});
        return session.id;
    },

    async select(sessionId) {
        const selectedId = parseInt(sessionId);
        if (this.currentSessionId === selectedId && Chat.isSending) return;
        const loading = {};
        this.activate(selectedId, loading);
        this.applyFilterAndRender();
        try {
            const res = await API.request(`/api/sessions/${sessionId}/messages`);
            const data = await API.readJSON(res);
            const messages = Array.isArray(data) ? data : (data.messages || []);
            if (this.loadingMessages === loading) Chat.loadMessages(messages);
        } catch (err) {
            if (this.loadingMessages === loading) {
                Chat.messagesContainer?.replaceChildren();
                this.showError(err);
            }
        } finally {
            if (this.loadingMessages === loading) this.activate(selectedId);
        }
    },

    toggleMenu(trigger, menu) {
        if (this.openMenu?.menu === menu) {
            this.closeMenu(true);
            return;
        }
        this.closeMenu();
        this.openMenu = {trigger, menu};
        menu.hidden = false;
        const rect = trigger.getBoundingClientRect();
        const bottom = window.visualViewport?.height || window.innerHeight;
        const below = rect.bottom + 4;
        menu.style.top = `${below + menu.offsetHeight <= bottom ? below : Math.max(4, rect.top - menu.offsetHeight - 4)}px`;
        menu.style.left = `${Math.max(4, rect.right - menu.offsetWidth)}px`;
        trigger.setAttribute('aria-expanded', 'true');
        menu.firstElementChild.focus();
    },

    closeMenu(restoreFocus = false) {
        if (!this.openMenu) return false;
        const {trigger, menu} = this.openMenu;
        this.openMenu = null;
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        if (restoreFocus) trigger.focus({preventScroll: true});
        return true;
    },

    async deleteSession(event, sessionId) {
        event.stopPropagation();
        if (!confirm(I18N.t('session_delete_confirm'))) return;
        const selectedId = parseInt(sessionId);
        if (this.currentSessionId === selectedId) Chat.dictation?.cancel();
        try {
            await API.deleteSession(sessionId);
            if (this.currentSessionId === selectedId) this.activate(null);
            Chat.forgetSession(selectedId);
            await this.load();
        } catch (err) {
            this.showError(err);
        }
    },

    async pinSession(event, sessionId) {
        event.stopPropagation();
        try {
            const result = await API.pinSession(sessionId);
            if (result.success) await this.load();
        } catch (err) {
            this.showError(err);
        }
    },

    downloadSession(event, sessionId) {
        event.stopPropagation();
        API.request(`/api/sessions/${sessionId}/download`)
            .then(async response => {
                if (!response.ok) await API.readJSON(response);
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
                    this.showError(err);
            });
    },

    init() {
        document.getElementById('session-filter').addEventListener('change', event => {
            this.currentFilter = event.target.value;
            this.applyFilterAndRender();
        });
        document.querySelector('.sidebar__chat-scroll').addEventListener('scroll', () => {
            this.closeMenu(this.openMenu?.menu.contains(document.activeElement));
        });
        document.addEventListener('click', event => {
            const open = this.openMenu;
            if (open && !open.menu.contains(event.target) && !open.trigger.contains(event.target)) this.closeMenu();
        });
        document.querySelector('.btn-new-chat').addEventListener('click', () => {
            window.dispatchEvent(new Event('conversationselected'));
            this.create().catch(error => this.showError(error));
        });
        window.addEventListener('languagechange', () => this.updateThreadHeading());
        this.load();
    },
};
