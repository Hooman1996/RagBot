const Dashboard = {
  chatHistory: [],

  async init() {
    this.bindEvents();
    await this.checkHealth();
  },

  async checkHealth() {
    const statusEl = document.getElementById("system-status");
    if (!statusEl) return;

    try {
      const data = await API.health();
      statusEl.innerHTML = `
        <span class="${data.system_initialized ? 'status-ok' : 'status-warn'}">
          ${data.system_initialized ? '🟢 System Ready' : '🟡 Not Initialized'}
        </span>
        &nbsp;|&nbsp;
        <span class="${data.ocr_available ? 'status-ok' : 'status-warn'}">
          OCR: ${data.ocr_available ? '✅' : '❌'}
        </span>
        &nbsp;|&nbsp;
        Docs: ${data.documents_available}
      `;
    } catch (err) {
      if (statusEl) statusEl.textContent = "🔴 API unreachable";
      console.error("Dashboard.checkHealth error:", err);
    }
  },

  onDocumentSelectionChanged(selectedDocs) {
    const badge = document.getElementById("selected-docs-badge");
    if (badge) {
      badge.textContent = selectedDocs.length > 0
        ? `${selectedDocs.length} doc(s) selected`
        : "All documents";
    }
  },

  async sendMessage() {
    const input = document.getElementById("chat-input");
    if (!input) return;

    const question = input.value.trim();
    if (!question) return;

    input.value = "";
    this.appendMessage("user", question);

    const selectedDocs = Sidebar.getSelectedDocuments();
    const topK = parseInt(document.getElementById("top-k")?.value || "2");
    const alpha = parseFloat(document.getElementById("alpha")?.value || "0.5");

    this.showTypingIndicator();

    try {
      const data = await API.query(question, selectedDocs, topK, alpha);
      this.hideTypingIndicator();

      if (data.status === "success") {
        this.appendMessage("bot", data.answer);
        this.renderSources(data.results);

        // Save messages to current session
        if (Sessions.currentSessionId) {
          await fetch(`/api/sessions/${Sessions.currentSessionId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'user', content: question })
          });
          await fetch(`/api/sessions/${Sessions.currentSessionId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'assistant', content: data.answer })
          });
          Sessions.load(); // refresh sidebar title
        }

      } else {
        this.appendMessage("bot", "⚠️ Error: " + (data.detail || "Unknown error"));
      }

    } catch (err) {
      this.hideTypingIndicator();
      this.appendMessage("bot", "❌ Failed to reach the server.");
      console.error("Dashboard.sendMessage error:", err);
    }
  },

  loadMessages(messages) {
    const chatBox = document.getElementById("chat-box");
    if (!chatBox) return;

    chatBox.innerHTML = "";
    this.chatHistory = [];

    messages.forEach(msg => {
      this.appendMessage(msg.role === "assistant" ? "bot" : "user", msg.content);
    });
  },

  appendMessage(role, text) {
    const chatBox = document.getElementById("chat-box");
    if (!chatBox) return;

    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.innerHTML = `<p>${text.replace(/\n/g, "<br>")}</p>`;

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;

    this.chatHistory.push({ role, text });
  },

  renderSources(results) {
    const sourcesEl = document.getElementById("sources-panel");
    if (!sourcesEl || !results || results.length === 0) return;

    sourcesEl.innerHTML = "<h4>📚 Sources</h4>";
    results.forEach(r => {
      const div = document.createElement("div");
      div.className = "source-item";
      div.innerHTML = `
        <strong>#${r.rank}</strong> — Score: ${r.score}
        <br><small>${r.content.substring(0, 150)}...</small>
      `;
      sourcesEl.appendChild(div);
    });
  },

  showTypingIndicator() {
    const chatBox = document.getElementById("chat-box");
    if (!chatBox) return;

    const div = document.createElement("div");
    div.className = "message bot typing";
    div.id = "typing-indicator";
    div.innerHTML = `<p>...</p>`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
  },

  hideTypingIndicator() {
    const el = document.getElementById("typing-indicator");
    if (el) el.remove();
  },

  async handleOCRUpload() {
    const fileInput = document.getElementById("ocr-file");
    if (!fileInput || !fileInput.files[0]) {
      alert("Please select a file first.");
      return;
    }

    const resultEl = document.getElementById("ocr-result");
    if (resultEl) resultEl.textContent = "Extracting...";

    try {
      const data = await API.ocrExtract(fileInput.files[0]);
      if (data.status === "success") {
        if (resultEl) resultEl.textContent = data.extracted_text;
      } else {
        if (resultEl) resultEl.textContent = "OCR failed: " + (data.detail || "Unknown error");
      }
    } catch (err) {
      if (resultEl) resultEl.textContent = "❌ OCR request failed.";
      console.error("Dashboard.handleOCRUpload error:", err);
    }
  },

  bindEvents() {
    const sendBtn = document.getElementById("send-btn");
    if (sendBtn) {
      sendBtn.addEventListener("click", () => this.sendMessage());
    }

    const input = document.getElementById("chat-input");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.sendMessage();
        }
      });
    }

    const ocrBtn = document.getElementById("ocr-upload-btn");
    if (ocrBtn) {
      ocrBtn.addEventListener("click", () => this.handleOCRUpload());
    }
  }
};

document.addEventListener("DOMContentLoaded", async () => {
  await Dashboard.init();
  await Sidebar.init();
});

document.addEventListener('session:selected', async ({ detail: { sessionId } }) => {
  const res = await fetch(`/api/sessions/${sessionId}`);
  const session = await res.json();
  Dashboard.loadMessages(session.messages);
});
