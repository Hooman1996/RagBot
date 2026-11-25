// static/js/chat.js

const Chat = {
  messagesContainer: null,
  textarea: null,
  sendBtn: null,
  selectedDocs: [],
  lockNotice: null,
  uploadInput: null,
  isLocked: true,
  uploadedDocText: null,
  uploadedDocName: null,
  uploadedDocSelected: false,
  disclosureId: 0,
  drafts: new Map(),
  attachments: new Map(),
  uploads: new Map(),

  init() {
    this.isSending = false;
    this.messagesContainer = document.getElementById("messages");
    this.transcript = document.getElementById("transcript");
    this.textarea = document.getElementById("chatInput");
    this.sendBtn = document.getElementById("sendBtn");
    this.lockNotice = document.getElementById("lockNotice");
    this._updateLockState();
    this.showWelcome();

    this.textarea.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.send();
      }
    });
    this.sendBtn.addEventListener("click", () => this.send());

    this._initUpload();
    const mic = document.getElementById("dictationMic");
    if (mic) this.dictation = new ChatDictation(this, mic);

    window.addEventListener('languagechange', () => {
      this.updatePlaceholder();
      this.renderDocumentScope();
    });
  },

  icon(name) {
    return `<svg class="chat-icon" aria-hidden="true" focusable="false"><use href="${document.body.dataset.iconsUrl || ''}#${name}"></use></svg>`;
  },

  showWelcome() {
    const template = document.getElementById("chat-welcome-template");
    if (!template || !this.messagesContainer) return;
    const welcome = template.content.cloneNode(true);
    I18N.applyLanguage(welcome);
    this.messagesContainer.replaceChildren(welcome);
  },

  scrollToBottom() {
    const scrollArea = this.transcript || this.messagesContainer;
    scrollArea.scrollTop = scrollArea.scrollHeight;
  },

  updatePlaceholder() {
    this.textarea.placeholder = I18N.t(this.isLocked ? 'lock_placeholder' : 'input_placeholder');
  },

  _updateLockState() {
    this.isLocked = !(this.selectedDocs.length || this.uploadedDocSelected);
    this.lockNotice.hidden = !this.isLocked;
    this.setSendingState(this.isSending);
    this.updatePlaceholder();
    if (this.isLocked) this.dictation?.cancel();
  },

  clearInvalidSelectedDocs(validDocNames) {
    this.selectedDocs = this.selectedDocs.filter(name => validDocNames.includes(name));
    this._updateLockState();
    this.renderDocumentScope();
  },

  toggleDocument(doc, allDocuments) {
    const selectedIndex = this.selectedDocs.indexOf(doc.name);
    if (selectedIndex >= 0) {
      this.selectedDocs.splice(selectedIndex, 1);
    } else {
      const first = allDocuments.find(item => item.name === this.selectedDocs[0]);
      if (first && first.category !== doc.category) {
        alert(I18N.t('category_warning'));
        return false;
      }
      this.selectedDocs.push(doc.name);
    }
    this._updateLockState();
    this.renderDocumentScope();
    return true;
  },

  renderDocumentScope() {
    const count = document.getElementById("selected-document-count");
    if (!count) return;
    const number = new Intl.NumberFormat(I18N.lang).format(this.selectedDocs.length);
    count.textContent = I18N.t('chat_selected_count', {count: number});
    const scope = document.getElementById("composer-scope");
    const names = document.getElementById("selected-document-names");
    scope.hidden = !this.selectedDocs.length;
    names.replaceChildren(...this.selectedDocs.map(name => {
      const label = document.createElement("bdi");
      label.textContent = name;
      return label;
    }));
  },

  renderAttachment() {
    const context = document.getElementById("docFilters");
    context.replaceChildren();
    if (!this.uploadedDocName) return;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "attachment-toggle";
    toggle.dataset.i18nTitle = 'chat_toggle_upload';
    toggle.title = I18N.t('chat_toggle_upload');
    toggle.setAttribute('aria-pressed', String(this.uploadedDocSelected));
    toggle.innerHTML = this.icon('documents');
    const name = document.createElement("bdi");
    name.textContent = this.uploadedDocName;
    toggle.appendChild(name);
    toggle.addEventListener("click", () => {
      this.uploadedDocSelected = !this.uploadedDocSelected;
      toggle.setAttribute('aria-pressed', String(this.uploadedDocSelected));
      this._updateLockState();
    });
    context.appendChild(toggle);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-button";
    remove.dataset.i18nLabel = 'remove_upload';
    remove.dataset.i18nTitle = 'remove_upload';
    remove.title = I18N.t('remove_upload');
    remove.setAttribute('aria-label', remove.title);
    remove.innerHTML = this.icon('close');
    remove.addEventListener("click", () => {
      this._clearUploadedDoc();
      this.setOcrStatus('');
      this.uploadButton.focus();
    });
    context.appendChild(remove);
  },

  _initUpload() {
    this.uploadInput = document.createElement("input");
    this.uploadInput.type = "file";
    this.uploadInput.accept = ".png,.jpg,.jpeg,.tiff,.bmp,.gif,.webp,.pdf";
    this.uploadInput.hidden = true;
    this.uploadInput.id = "hiddenFileInput";
    document.body.appendChild(this.uploadInput);
    this.uploadInput.addEventListener("change", event => {
      const file = event.target.files[0];
      this.uploadInput.value = "";
      if (file) this._handleFileUpload(file);
    });

    this.uploadButton = document.createElement("button");
    this.uploadButton.type = "button";
    this.uploadButton.className = "btn-upload";
    this.uploadButton.dataset.i18nLabel = 'upload_btn_title';
    this.uploadButton.dataset.i18nTitle = 'upload_btn_title';
    this.uploadButton.title = I18N.t('upload_btn_title');
    this.uploadButton.setAttribute('aria-label', this.uploadButton.title);
    this.uploadButton.id = "uploadFileBtn";
    this.uploadButton.innerHTML = this.icon('paperclip');
    this.uploadButton.addEventListener("click", () => this.uploadInput.click());

    const actions = document.querySelector(".chat-input-actions");
    actions.insertBefore(this.uploadButton, actions.firstChild);
  },

  setOcrStatus(key, error = false) {
    const status = document.getElementById('ocr-status');
    if (!status) return;
    if (key) status.dataset.i18n = key;
    else delete status.dataset.i18n;
    status.textContent = key ? I18N.t(key) : '';
    status.classList.toggle('error', error);
  },

  async _handleFileUpload(file) {
    const upload = { sessionId: Sessions.currentSessionId };
    if (this.uploads.has(upload.sessionId)) return;
    this.uploads.set(upload.sessionId, upload);
    this.uploadButton.disabled = true;
    this.setOcrStatus('chat_ocr_processing');
    let key = 'chat_ocr_error';
    try {
      const res = await API.ocrExtract(file);
      if (res.status === "success") {
        const text = res.extracted_text?.trim();
        key = text ? 'chat_ocr_ready' : 'chat_ocr_empty';
        if (text && this.uploads.get(upload.sessionId) === upload) {
          const attachment = {text, name: file.name, selected: true};
          if (Sessions.currentSessionId === upload.sessionId) this.restoreAttachment(attachment);
          else this.attachments.set(upload.sessionId, attachment);
        }
      }
    } catch (_) {
      // Use the localized status without exposing service internals.
    } finally {
      if (this.uploads.get(upload.sessionId) === upload) {
        this.uploads.delete(upload.sessionId);
        if (Sessions.currentSessionId === upload.sessionId) {
          this.uploadButton.disabled = false;
          this.setOcrStatus(key, key !== 'chat_ocr_ready');
        }
      }
    }
  },

  restoreAttachment(attachment) {
    this.uploadedDocText = attachment?.text ?? null;
    this.uploadedDocName = attachment?.name ?? null;
    this.uploadedDocSelected = attachment?.selected ?? false;
    this.renderAttachment();
    this._updateLockState();
  },

  _clearUploadedDoc() {
    this.restoreAttachment(null);
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
    this.labelButton(copyBtn, 'feedback_copy');
    copyBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    copyBtn.addEventListener("click", () => {
      const bubble = bar.closest(".message__body").querySelector(".message__bubble");
      Promise.resolve().then(() => navigator.clipboard.writeText(bubble.textContent)).then(() => {
        copyBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
        copyBtn.classList.add("feedback-btn--active");
        setTimeout(() => {
          copyBtn.classList.remove("feedback-btn--active");
          copyBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
        }, 2000);
      }).catch(() => {
        if (bar.isConnected) this.showError({localeKey: 'chat_copy_error'});
      });
    });

    bar.appendChild(copyBtn);
    if (!queryId && !(satisfactionNeeded && sessionId)) return bar;

    // Like button
    const likeBtn = document.createElement("button");
    likeBtn.className = "feedback-btn feedback-btn--like" + (existingHelpful === 1 ? " feedback-btn--active" : "");
    this.labelButton(likeBtn, 'feedback_helpful');
    likeBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>`;

    // Dislike button
    const dislikeBtn = document.createElement("button");
    dislikeBtn.className = "feedback-btn feedback-btn--dislike" + (existingHelpful === 0 ? " feedback-btn--active" : "");
    this.labelButton(dislikeBtn, 'feedback_not_helpful');
    dislikeBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>`;

    // Comment button
    const commentBtn = document.createElement("button");
    commentBtn.className = "feedback-btn feedback-btn--comment" + (existingComment ? " feedback-btn--active" : "");
    this.labelButton(commentBtn, 'feedback_comment');
    commentBtn.innerHTML = `<svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;

    likeBtn.setAttribute('aria-pressed', String(existingHelpful === 1));
    dislikeBtn.setAttribute('aria-pressed', String(existingHelpful === 0));
    commentBtn.setAttribute('aria-expanded', 'false');

    const commentPanel = document.createElement("div");
    commentPanel.className = "feedback-comment-panel";
    commentPanel.hidden = true;
    commentPanel.innerHTML = `
      <textarea class="feedback-comment-input" dir="auto" data-i18n-label="feedback_comment"
        data-i18n-placeholder="feedback_comment_placeholder" rows="2"></textarea>
      <button class="feedback-comment-submit" type="button" data-i18n="feedback_comment_submit"></button>
    `;
    I18N.applyLanguage(commentPanel);
    commentPanel.querySelector(".feedback-comment-input").value = existingComment;

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
        likeBtn.setAttribute('aria-pressed', String(newVal === 1));
        dislikeBtn.setAttribute('aria-pressed', String(newVal === 0));
      } catch (error) {
        if (bar.isConnected) this.showError(error);
      }
    };

    likeBtn.addEventListener("click", () => setFeedback(1));
    dislikeBtn.addEventListener("click", () => setFeedback(0));

    commentBtn.addEventListener("click", () => {
      commentPanel.hidden = !commentPanel.hidden;
      commentBtn.setAttribute('aria-expanded', String(!commentPanel.hidden));
      if (!commentPanel.hidden) commentPanel.querySelector(".feedback-comment-input").focus();
    });

    commentPanel.querySelector(".feedback-comment-submit").addEventListener("click", async () => {
      const input = commentPanel.querySelector(".feedback-comment-input");
      const text = input.value.trim();
      if (!text || !queryId) return;
      try {
        await API.submitComment(queryId, text);
        commentBtn.classList.add("feedback-btn--active");
        commentPanel.hidden = true;
        commentBtn.setAttribute('aria-expanded', 'false');
        commentBtn.focus();
      } catch (error) {
        if (bar.isConnected) this.showError(error);
      }
    });

    if (queryId) {
      bar.appendChild(likeBtn);
      bar.appendChild(dislikeBtn);
      bar.appendChild(commentBtn);
      bar.appendChild(commentPanel);
    }

    // --- Ticket button (new) ---
    if (satisfactionNeeded && sessionId) {
      const ticketBtn = document.createElement("button");
      ticketBtn.className = "feedback-btn feedback-btn--ticket";
      this.labelButton(ticketBtn, 'feedback_submit_ticket');
      ticketBtn.innerHTML = `
        <svg aria-hidden="true" focusable="false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" style="vertical-align:middle;">
          <path d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/>
        </svg>
        <span dir="auto" data-i18n="feedback_submit_ticket">${I18N.t('feedback_submit_ticket')}</span>
      `;

      ticketBtn.addEventListener("click", async () => {
        ticketBtn.disabled = true;
        const status = document.createElement('span');
        status.dir = 'auto';
        status.setAttribute('role', 'status');
        try {
          await API.submitSatisfaction(sessionId, false);
          status.dataset.i18n = 'chat_ticket_received';
          status.className = 'ticket-confirmation';
          ticketBtn.replaceWith(status);
        } catch (_) {
          status.dataset.i18n = 'ticket_error';
          status.className = 'ticket-error';
          ticketBtn.disabled = false;
          bar.querySelector('.ticket-error')?.remove();
          bar.appendChild(status);
        }
        status.textContent = I18N.t(status.dataset.i18n);
      });

      bar.appendChild(ticketBtn);
    }

    return bar;
  },

  labelButton(button, key) {
    button.type = 'button';
    button.dataset.i18nLabel = key;
    button.dataset.i18nTitle = key;
    button.title = I18N.t(key);
    button.setAttribute('aria-label', button.title);
  },

  _buildMessage(role, text, timeStr = null, queryId = null,
                isHelpful = null, metaData = {}, satisfactionNeeded = false,
                relatedQuestions = [], pending = false) {
    const isUser = role === "user";
    const msg = document.createElement("article");
    msg.className = `message ${isUser ? "message--user" : "message--ai"}`;
    const sender = isUser ? 'chat_you' : 'chat_assistant';

    msg.innerHTML = `
      ${isUser ? '' : `<div class="message__avatar"><img src="${document.body.dataset.bankLogo}" alt="" width="32" height="32"></div>`}
      <div class="message__body">
        <div class="message__heading">
          <span class="message__sender" dir="auto" data-i18n="${sender}"></span>
          <bdi class="message__time"></bdi>
        </div>
        <div class="message__bubble" dir="auto"></div>
      </div>
    `;
    msg.querySelector('.message__sender').textContent = I18N.t(sender);
    msg.querySelector('.message__time').textContent = timeStr || this._timeStr();
    msg.querySelector(".message__bubble").textContent = text;
    if (!isUser && !pending) {
      this._addAnswerControls(msg.querySelector(".message__body"), queryId,
        isHelpful, metaData, satisfactionNeeded, relatedQuestions);
    }
    return msg;
  },

  _addAnswerControls(body, queryId, isHelpful, metaData, satisfactionNeeded, relatedQuestions) {
    body.appendChild(this._buildFeedbackBar(
      queryId, isHelpful, metaData?.user_comment || "", satisfactionNeeded, Sessions.currentSessionId
    ));
    if (!relatedQuestions.length) return;

    const questions = document.createElement("div");
    questions.className = "message__related-questions";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "related-toggle";
    toggle.innerHTML = `${this.icon('chevron-down')}<span dir="auto" data-i18n="sources_related_questions"></span>`;
    toggle.lastElementChild.textContent = I18N.t('sources_related_questions');
    toggle.setAttribute('aria-expanded', 'false');
    const list = document.createElement("ul");
    list.className = "related-questions-list";
    list.hidden = true;
    list.id = `related-${++this.disclosureId}`;
    toggle.setAttribute('aria-controls', list.id);
    toggle.addEventListener('click', () => {
      list.hidden = !list.hidden;
      toggle.setAttribute('aria-expanded', String(!list.hidden));
    });

    let opened = null;
    for (const item of relatedQuestions) {
      const row = document.createElement("li");
      row.className = "related-question-item";
      const question = document.createElement("button");
      question.type = "button";
      question.className = "related-question-toggle";
      question.dir = 'auto';
      question.textContent = item.question;
      question.setAttribute('aria-expanded', 'false');
      const answer = document.createElement("div");
      answer.className = "related-answer";
      answer.dir = 'auto';
      answer.textContent = item.answer;
      answer.id = `related-${++this.disclosureId}`;
      answer.hidden = true;
      question.setAttribute('aria-controls', answer.id);
      question.addEventListener('click', () => {
        const alreadyOpen = !answer.hidden;
        if (opened) {
          opened.answer.hidden = true;
          opened.question.setAttribute('aria-expanded', 'false');
        }
        if (alreadyOpen) {
          opened = null;
        } else {
          opened = {question, answer};
          answer.hidden = false;
          question.setAttribute('aria-expanded', 'true');
        }
      });
      row.appendChild(question);
      row.appendChild(answer);
      list.appendChild(row);
    }
    questions.appendChild(toggle);
    questions.appendChild(list);
    body.appendChild(questions);
  },

  addUserMessage(text, timeStr = null) {
    const msg = this._buildMessage("user", text, timeStr);
    this.messagesContainer.querySelector?.('.chat-welcome')?.remove();
    this.messagesContainer.appendChild(msg);
    this.scrollToBottom();
  },

  addAIMessage(text, timeStr = null, queryId = null,
               isHelpful = null, metaData = {}, satisfactionNeeded = false,
               relatedQuestions = []) {
    const msg = this._buildMessage("assistant", text, timeStr, queryId,
                                   isHelpful, metaData, satisfactionNeeded,
                                   relatedQuestions);
    this.messagesContainer.querySelector?.('.chat-welcome')?.remove();
    this.messagesContainer.appendChild(msg);
    this.scrollToBottom();
  },

  loadMessages(messages) {
    this.messagesContainer.replaceChildren();
    if (!messages.length) this.showWelcome();
    messages.forEach(m => {
      const timeStr = m.created_at
        ? new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : null;
      const msg = this._buildMessage(m.role, m.content, timeStr, m.id || null,
                                     m.is_helpful ?? null, m.meta_data || {}, false, []);
      this.messagesContainer.appendChild(msg);
    });
    this.scrollToBottom();
  },

  pendingStatus(key) {
    const element = document.createElement("div");
    element.className = 'typing-indicator';
    element.setAttribute('role', 'status');
    element.dataset.i18n = key;
    element.textContent = I18N.t(key);
    this.messagesContainer.appendChild(element);
    return element;
  },

  showLoading() {
    if (this.transcript) this.pendingStatus('chat_loading_messages');
  },

  sessionChanged(previousId, sessionId, carryDraft) {
    this.activeStream?.abort();
    this.messagesContainer?.replaceChildren();
    if (!this.textarea) return;

    if (carryDraft) {
      const upload = this.uploads.get(previousId);
      if (upload) {
        this.uploads.delete(previousId);
        upload.sessionId = sessionId;
        this.uploads.set(sessionId, upload);
      }
      this.drafts.delete(previousId);
      this.attachments.delete(previousId);
    } else {
      if (this.textarea.value) this.drafts.set(previousId, this.textarea.value);
      else this.drafts.delete(previousId);
      if (this.uploadedDocName) {
        this.attachments.set(previousId, {
          text: this.uploadedDocText, name: this.uploadedDocName, selected: this.uploadedDocSelected,
        });
      } else {
        this.attachments.delete(previousId);
      }
      this.textarea.value = this.drafts.get(sessionId) || '';
      this.restoreAttachment(this.attachments.get(sessionId));
      const processing = this.uploads.has(sessionId);
      if (this.uploadButton) this.uploadButton.disabled = processing;
      this.setOcrStatus(processing ? 'chat_ocr_processing' : '');
    }
    if (!Sessions.loadingMessages) this.showWelcome();
  },

  forgetSession(sessionId) {
    this.drafts.delete(sessionId);
    this.attachments.delete(sessionId);
    this.uploads.delete(sessionId);
  },

  setSendingState(isSending) {
    this.isSending = isSending;
    const disabled = !!(isSending || this.isLocked || Sessions.loadingMessages);
    this.sendBtn.disabled = disabled;
    this.textarea.disabled = disabled;
    this.dictation?.render();
  },

  showError(error) {
    const message = document.createElement("div");
    message.className = "message message--error";
    message.dir = 'auto';
    message.setAttribute("role", "alert");
    if (I18N.lang) {
      message.dataset.i18n = error?.localeKey ?? 'chat_error_generic';
      message.textContent = I18N.t(message.dataset.i18n);
    } else {
      message.textContent = API.errorMessage(error);
    }
    (this.messagesContainer || document.getElementById("messages"))?.appendChild(message);
    if (this.messagesContainer) this.scrollToBottom();
  },

  async send() {
    if (this.isSending || this.isLocked || Sessions.loadingMessages) return;
    const text = this.textarea.value.trim();
    if (!text) return;

    const documents = this.selectedDocs.slice();
    const uploadedText = this.uploadedDocSelected ? this.uploadedDocText : null;
    const uploadedName = this.uploadedDocName;
    const returnFocus = document.activeElement === this.textarea || document.activeElement === this.sendBtn;
    this.setSendingState(true);
    this.dictation?.cancel();
    let sessionId, indicator, reply, bubble, controller;
    const isCurrent = () => !controller?.signal.aborted &&
      sessionId === Number(Sessions.currentSessionId);
    try {
      sessionId = Number(await Sessions.ensureSession());
      if (!isCurrent()) return;
      controller = new AbortController();
      this.activeStream = controller;

      const finalQuery = uploadedText
        ? `[فایل بارگذاری‌شده: ${uploadedName}]\n${uploadedText}\n\nسوال:\n${text}`
        : text;

      this.addUserMessage(text);
      this.textarea.value = "";
      indicator = this.pendingStatus('chat_thinking');
      indicator.id = 'typing';
      this.scrollToBottom();
      const res = await API.streamQuery({
        query: finalQuery, documents, session_id: sessionId,
        top_k: 10, alpha: 0.5, uploaded_text: uploadedText || null,
      }, {
        signal: controller.signal,
        onDelta: (text) => {
          if (!isCurrent() || (!bubble && !text.trim())) return;
          const scrollArea = this.transcript || this.messagesContainer;
          const follow = scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 80;
          if (!bubble) {
            indicator.remove();
            reply = this._buildMessage("assistant", "", null, null, null, {}, false, [], true);
            bubble = reply.querySelector(".message__bubble");
            this.messagesContainer.appendChild(reply);
          }
          bubble.append(document.createTextNode(text));
          if (follow) this.scrollToBottom();
        },
      });
      if (!isCurrent()) return;
      if (bubble) {
        bubble.textContent = res.answer;
        this._addAnswerControls(reply.querySelector(".message__body"), res.query_id,
          null, {}, res.feedback_needed === true, res.related_questions || []);
        const {scrollHeight, scrollTop, clientHeight} = this.transcript || this.messagesContainer;
        if (scrollHeight - scrollTop - clientHeight < 110) this.scrollToBottom();
      } else {
        indicator.remove();
        this.addAIMessage(res.answer, null, res.query_id, null, {},
          res.feedback_needed === true, res.related_questions || []);
      }
      Sessions.load();
    } catch (err) {
      reply?.remove();
      if (sessionId === undefined || isCurrent()) this.showError(err);
    } finally {
      indicator?.remove();
      if (this.activeStream === controller) this.activeStream = null;
      this.isSending = false;
      this._updateLockState();
      if (returnFocus && isCurrent() && !this.textarea.disabled &&
          document.activeElement === document.body && !this.textarea.closest?.('[inert]')) {
        this.textarea.focus({preventScroll: true});
      }
    }
  }
};
