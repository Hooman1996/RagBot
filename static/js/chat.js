// static/js/chat.js

const Chat = {
  messagesContainer: null,
  textarea: null,
  sendBtn: null,
  selectedDocs: [],
  allDocuments: [],
  lockNotice: null,
  uploadInput: null,
  isLocked: true,
  uploadedDocText: null,
  uploadedDocName: null,
  uploadedDocSelected: false,
  filteredDocs: [],

  async init() {
    this.isSending = false;
    this.messagesContainer = document.getElementById("messages");
    this.textarea = document.getElementById("chatInput");
    this.sendBtn = document.getElementById("sendBtn");
    this.lockNotice = document.getElementById("lockNotice");

    this.textarea.placeholder = I18N.t('input_placeholder');

    this._updateLockState();

    this.textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });

    this.sendBtn.addEventListener("click", () => this.send());

    this._initUpload();

    if (typeof CategoryFilter !== 'undefined') {
      if (CategoryFilter.allDocuments.length) {
        this.allDocuments = CategoryFilter.allDocuments;
        this.renderDocumentTags(this.allDocuments);
      } else {
        window.addEventListener('categoryFilterLoaded', () => {
          this.allDocuments = CategoryFilter.allDocuments;
          this.renderDocumentTags(this.allDocuments);
        });
      }
    } else {
      await this.loadDocuments();
    }

    // Update dynamic labels when language changes
    window.addEventListener('languagechange', () => {
      // Update any existing ticket buttons inside feedback bars
      document.querySelectorAll('.feedback-btn--ticket span').forEach(span => {
        span.textContent = I18N.t('feedback_submit_ticket');
      });
      // Update related questions toggle buttons
      document.querySelectorAll('.related-toggle').forEach(btn => {
        btn.textContent = I18N.t('sources_related_questions');
      });
    });
  },

  async loadDocuments() {
    try {
      const data = await API.getDocuments();
      this.allDocuments = data.documents || [];
      if (typeof CategoryFilter !== 'undefined') {
        CategoryFilter.allDocuments = this.allDocuments;
        CategoryFilter.applyFilter();
      } else {
        this.renderDocumentTags(this.allDocuments);
      }
    } catch(e) {
      console.error(e);
    }
  },

  _updateLockState() {
    const shouldUnlock = this.selectedDocs.length > 0 || this.uploadedDocSelected;
    this.isLocked = !shouldUnlock;

    if (this.isLocked) {
      this.lockNotice.style.display = 'flex';
      this.textarea.disabled = true;
      this.sendBtn.disabled = true;
      this.textarea.placeholder = I18N.t('lock_placeholder') || 'برای پرسش، ابتدا یک سند انتخاب یا آپلود کنید';
    } else {
      this.lockNotice.style.display = 'none';
      this.textarea.disabled = false;
      this.sendBtn.disabled = false;
      this.textarea.placeholder = I18N.t('input_placeholder');
    }
  },

  clearInvalidSelectedDocs(validDocNames) {
    this.selectedDocs = this.selectedDocs.filter(name => validDocNames.includes(name));
    this._updateLockState();
    this._renderAllTags();
  },

  updateDocumentTags(filteredDocs) {
    this.filteredDocs = filteredDocs;
    this._renderAllTags();
  },

  renderDocumentTags(docs) {
    this.filteredDocs = docs;
    this._renderAllTags();
  },

  _renderAllTags() {
    const bar = document.getElementById("docFilters");
    if (!bar) return;
    bar.innerHTML = '';

    this.filteredDocs.forEach(doc => {
      const tag = document.createElement("div");
      tag.className = "doc-tag";
      if (this.selectedDocs.includes(doc.name)) {
        tag.classList.add("selected");
      }
      tag.innerText = doc.name;
      tag.dataset.category = doc.category;

      // ─── FIXED: category‑lock enforcement ──────────────────
      tag.onclick = () => {
        // If there is already a selected document, check category
        if (this.selectedDocs.length > 0) {
          const firstSelected = this.allDocuments.find(
            d => d.name === this.selectedDocs[0]
          );
          if (firstSelected && firstSelected.category !== doc.category) {
            alert(I18N.t('category_warning') ||
                  "شما تنها می‌توانید اسناد از یک دسته انتخاب کنید.");
            return;
          }
        }

        // Toggle selection
        tag.classList.toggle("selected");
        const idx = this.selectedDocs.indexOf(doc.name);
        if (idx > -1) {
          this.selectedDocs.splice(idx, 1);
        } else {
          this.selectedDocs.push(doc.name);
        }
        this._updateLockState();
        this._renderAllTags();
      };
      // ───────────────────────────────────────────────────────

      bar.appendChild(tag);
    });

    // Uploaded file tag
    if (this.uploadedDocName) {
      const tag = document.createElement("div");
      tag.className = `doc-tag uploaded-doc-tag${this.uploadedDocSelected ? ' selected' : ''}`;
      tag.innerHTML = `📄 ${this.uploadedDocName} <span class="remove-upload" title="${I18N.t('remove_upload') || 'حذف کامل فایل'}">×</span>`;
      tag.addEventListener("click", (e) => {
        if (e.target.classList.contains("remove-upload")) {
          e.stopPropagation();
          this._clearUploadedDoc();
          return;
        }
        this.uploadedDocSelected = !this.uploadedDocSelected;
        tag.classList.toggle("selected", this.uploadedDocSelected);
        this._updateLockState();
      });
      bar.appendChild(tag);
    }

    this._updateLockState();
  },

  _initUpload() {
    if (document.getElementById('uploadFileBtn')) return;

    this.uploadInput = document.createElement("input");
    this.uploadInput.type = "file";
    this.uploadInput.accept = ".png,.jpg,.jpeg,.tiff,.bmp,.gif,.webp,.pdf";
    this.uploadInput.style.display = "none";
    this.uploadInput.id = "hiddenFileInput";
    document.body.appendChild(this.uploadInput);
    this.uploadInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      this._handleFileUpload(file);
    });

    const uploadBtn = document.createElement("button");
    uploadBtn.className = "btn-upload";
    uploadBtn.title = I18N.t('upload_btn_title') || "بارگذاری فایل (تصویر یا PDF)";
    uploadBtn.id = "uploadFileBtn";
    uploadBtn.innerHTML = `<span aria-hidden="true">📎</span>`;
    uploadBtn.addEventListener("click", () => {
      this.uploadInput.click();
    });

    const actions = document.querySelector(".chat-input-actions");
    if (actions) {
      actions.insertBefore(uploadBtn, actions.firstChild);
    }
  },

  async _handleFileUpload(file) {
    try {
      const res = await API.ocrExtract(file);
      if (res.status === "success") {
        this.uploadedDocText = res.extracted_text.trim();
        this.uploadedDocName = file.name;
        this.uploadedDocSelected = true;
        this._updateLockState();
        this._renderAllTags();
      } else {
        alert("خطا در استخراج متن از فایل: " + (res.detail || "نامشخص"));
      }
    } catch (err) {
      console.error(err);
      alert("خطا در ارتباط با سرویس OCR");
    } finally {
      this.uploadInput.value = "";
    }
  },

  _clearUploadedDoc() {
    this.uploadedDocText = null;
    this.uploadedDocName = null;
    this.uploadedDocSelected = false;
    this._updateLockState();
    this._renderAllTags();
  },

  async ensureSession() {
    if (!Sessions.currentSessionId) {
      await Sessions.create();
    }
  },

  _timeStr() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  },

  /* ── Feedback toolbar (copy / like / dislike / comment / ticket) ── */
  _buildFeedbackBar(queryId, existingHelpful = null, existingComment = "",
                     satisfactionNeeded = false, sessionId = null) {
    const bar = document.createElement("div");
    bar.className = "message__feedback";

    // Copy button
    const copyBtn = document.createElement("button");
    copyBtn.className = "feedback-btn feedback-btn--copy";
    copyBtn.title = I18N.t('feedback_copy');
    copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    copyBtn.addEventListener("click", () => {
      const bubble = bar.closest(".message__body").querySelector(".message__bubble");
      navigator.clipboard.writeText(bubble.innerText).then(() => {
        copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
        copyBtn.classList.add("feedback-btn--active");
        setTimeout(() => {
          copyBtn.classList.remove("feedback-btn--active");
          copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
        }, 2000);
      });
    });

    // Like button
    const likeBtn = document.createElement("button");
    likeBtn.className = "feedback-btn feedback-btn--like" + (existingHelpful === 1 ? " feedback-btn--active" : "");
    likeBtn.title = I18N.t('feedback_helpful');
    likeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>`;

    // Dislike button
    const dislikeBtn = document.createElement("button");
    dislikeBtn.className = "feedback-btn feedback-btn--dislike" + (existingHelpful === 0 ? " feedback-btn--active" : "");
    dislikeBtn.title = I18N.t('feedback_not_helpful');
    dislikeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>`;

    // Comment button
    const commentBtn = document.createElement("button");
    commentBtn.className = "feedback-btn feedback-btn--comment" + (existingComment ? " feedback-btn--active" : "");
    commentBtn.title = I18N.t('feedback_comment');
    commentBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;

    // Comment panel
    const commentPanel = document.createElement("div");
    commentPanel.className = "feedback-comment-panel";
    commentPanel.style.display = "none";
    commentPanel.innerHTML = `
      <textarea class="feedback-comment-input" placeholder="${I18N.t('feedback_comment_placeholder')}" rows="2">${existingComment}</textarea>
      <button class="feedback-comment-submit">${I18N.t('feedback_comment_submit')}</button>
    `;

    // Like/dislike handlers
    const setFeedback = async (value) => {
      if (!queryId) return;
      const newVal = (value === 1 && likeBtn.classList.contains("feedback-btn--active")) ? null
                   : (value === 0 && dislikeBtn.classList.contains("feedback-btn--active")) ? null
                   : value;
      try {
        await API.submitFeedback(queryId, newVal);
        likeBtn.classList.toggle("feedback-btn--active", newVal === 1);
        dislikeBtn.classList.toggle("feedback-btn--active", newVal === 0);
      } catch(e) { console.error("Feedback error:", e); }
    };

    likeBtn.addEventListener("click", () => setFeedback(1));
    dislikeBtn.addEventListener("click", () => setFeedback(0));

    commentBtn.addEventListener("click", () => {
      commentPanel.style.display = commentPanel.style.display === "none" ? "flex" : "none";
    });

    commentPanel.querySelector(".feedback-comment-submit").addEventListener("click", async () => {
      const input = commentPanel.querySelector(".feedback-comment-input");
      const text = input.value.trim();
      if (!text || !queryId) return;
      try {
        await API.submitComment(queryId, text);
        commentBtn.classList.add("feedback-btn--active");
        commentPanel.style.display = "none";
      } catch(e) { console.error("Comment error:", e); }
    });

    bar.appendChild(copyBtn);
    bar.appendChild(likeBtn);
    bar.appendChild(dislikeBtn);
    bar.appendChild(commentBtn);
    bar.appendChild(commentPanel);

    // --- Ticket button (new) ---
    if (satisfactionNeeded && sessionId) {
      const ticketBtn = document.createElement("button");
      ticketBtn.className = "feedback-btn feedback-btn--ticket";
      ticketBtn.title = I18N.t('feedback_submit_ticket');
      ticketBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" style="vertical-align:middle;">
          <path d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/>
        </svg>
        <span>${I18N.t('feedback_submit_ticket')}</span>
      `;

      ticketBtn.addEventListener("click", async () => {
        const btn = ticketBtn; // capture reference
        try {
          const response = await API.submitSatisfaction(sessionId, false);
          btn.outerHTML = `<span class="ticket-confirmation">${response.confirmation}</span>`;
        } catch (err) {
          console.error("Ticket error:", err);
          btn.outerHTML = `<span class="ticket-error">${I18N.t('ticket_error') || "خطا در ارسال تیکت"}</span>`;
        }
      });

      bar.appendChild(ticketBtn);
    }

    return bar;
  },

  /* ── Build a message element ── */
  _buildMessage(role, text, timeStr = null, queryId = null,
                isHelpful = null, metaData = {}, satisfactionNeeded = false,
                relatedQuestions = []) {
    const isUser = role === "user";
    const msg = document.createElement("div");
    msg.className = `message ${isUser ? "message--user" : "message--ai"}`;
    const time = timeStr || this._timeStr();

    msg.innerHTML = `
      <div class="message__avatar">${isUser ? "U" : "AI"}</div>
      <div class="message__body">
        <div class="message__sender">${isUser ? I18N.t('You') : I18N.t('AI')}</div>
        <div class="message__bubble" dir="auto">${text}</div>
        <div class="message__meta">
          <span class="message__time">${time}</span>
        </div>
      </div>
    `;

    const body = msg.querySelector(".message__body");

    // Feedback bar (with optional ticket button) – only for AI messages
    if (!isUser) {
      const comment = metaData?.user_comment || "";
      const feedbackBar = this._buildFeedbackBar(
        queryId, isHelpful, comment,
        satisfactionNeeded, Sessions.currentSessionId
      );
      body.appendChild(feedbackBar);
    }

    // Most Related Questions collapsible section
    if (!isUser && relatedQuestions.length > 0) {
      const questionsContainer = document.createElement("div");
      questionsContainer.className = "message__related-questions";

      const toggleBtn = document.createElement("button");
      toggleBtn.className = "sources-toggle related-toggle";
      toggleBtn.textContent = I18N.t('sources_related_questions') || "Most Related Questions";

      const panel = document.createElement("div");
      panel.className = "related-panel sources-panel";
      panel.style.display = "none";
      panel.dir = "rtl";

      const list = document.createElement("ul");
      list.className = "related-questions-list";

      relatedQuestions.forEach((item) => {
        const li = document.createElement("li");
        li.className = "related-question-item";
        li.textContent = item.question;

        // Create hidden answer area
        const answerDiv = document.createElement("div");
        answerDiv.className = "related-answer";
        answerDiv.textContent = item.answer;
        answerDiv.style.display = "none";
        li.appendChild(answerDiv);

        // Click toggles answer visibility
        li.addEventListener("click", () => {
          const isVisible = answerDiv.style.display === "block";
          // Hide all other answer divs first (accordion behavior)
          list.querySelectorAll('.related-answer').forEach(el => el.style.display = "none");
          answerDiv.style.display = isVisible ? "none" : "block";
        });

        list.appendChild(li);
      });

      panel.appendChild(list);
      questionsContainer.appendChild(toggleBtn);
      questionsContainer.appendChild(panel);
      body.appendChild(questionsContainer);

      toggleBtn.addEventListener("click", () => {
        panel.style.display = panel.style.display === "none" ? "block" : "none";
      });
    }

    return msg;
  },

  addUserMessage(text, timeStr = null) {
    const msg = this._buildMessage("user", text, timeStr);
    this.messagesContainer.appendChild(msg);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  },

  addAIMessage(text, timeStr = null, queryId = null,
               isHelpful = null, metaData = {}, satisfactionNeeded = false,
               relatedQuestions = []) {
    const msg = this._buildMessage("assistant", text, timeStr, queryId,
                                   isHelpful, metaData, satisfactionNeeded,
                                   relatedQuestions);
    this.messagesContainer.appendChild(msg);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  },

  loadMessages(messages) {
    this.messagesContainer.innerHTML = "";
    messages.forEach(m => {
      const timeStr = m.created_at
        ? new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : null;
      const msg = this._buildMessage(m.role, m.content, timeStr, m.id || null,
                                     m.is_helpful ?? null, m.meta_data || {}, false, []);
      this.messagesContainer.appendChild(msg);
    });
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  },

  typing() {
    const el = document.createElement("div");
    el.className = "typing-indicator";
    el.id = "typing";
    el.innerHTML = `
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    `;
    this.messagesContainer.appendChild(el);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  },

  removeTyping() {
    const el = document.getElementById("typing");
    if (el) el.remove();
  },

  setSendingState(isSending) {
    this.isSending = isSending;
    this.sendBtn.disabled = isSending || this.isLocked;
    this.textarea.disabled = isSending || this.isLocked;
  },

  async send() {
    if (this.isSending || this.isLocked) return;
    this.isSending = true;

    const text = this.textarea.value.trim();
    if (!text) {
      this.isSending = false;
      return;
    }

    await Sessions.ensureSession();

    // Remove any pending satisfaction prompts
    document.querySelectorAll(".feedback-satisfaction").forEach(el => el.remove());

    let finalQuery = text;
    let uploadedTextToSend = null;
    if (this.uploadedDocSelected && this.uploadedDocText) {
      uploadedTextToSend = this.uploadedDocText;
      finalQuery = `[فایل بارگذاری‌شده: ${this.uploadedDocName}]\n${this.uploadedDocText}\n\nسوال:\n${text}`;
    }

    this.addUserMessage(text);
    this.textarea.value = "";
    this.typing();

    try {
      const res = await API.query(finalQuery, this.selectedDocs, Sessions.currentSessionId, 10, 0.5, uploadedTextToSend);
      this.removeTyping();

      if (res.status === "success") {
        const queryId = res.query_id || null;
        const satisfactionNeeded = res.feedback_needed === true;
        this.addAIMessage(
          res.answer,
          null,
          queryId,
          null,
          {},
          satisfactionNeeded,
          res.related_questions || []
        );
        Sessions.load();
      } else {
        this.addAIMessage("Error retrieving response.");
      }
    } catch (err) {
      console.error(err);
      this.removeTyping();
      this.addAIMessage("System error. Please try again.");
    } finally {
      this.isSending = false;
    }
  }
};