const API = {
  fallbackError: "خطایی در ارتباط با سامانه رخ داد. لطفاً دوباره تلاش کنید.",

  errorMessage(error) {
    return error?.publicMessage || this.fallbackError;
  },

  publicError(message) {
    const error = new Error(message);
    error.publicMessage = message;
    return error;
  },

  async request(url, options) {
    try {
      return await fetch(url, options);
    } catch (_) {
      throw this.publicError("ارتباط با سامانه برقرار نشد. اتصال شبکه را بررسی و دوباره تلاش کنید.");
    }
  },

  async readJSON(response) {
    let data;
    try { data = await response.json(); }
    catch (_) { throw this.publicError(this.fallbackError); }
    if (!response.ok || (data?.errorCode && data.errorCode !== "0" && data.errorCode !== 0)) {
      throw this.responseError(data, response.status);
    }
    return data;
  },

  responseError(data, status) {
    // Only known public errors are shown. Never echo arbitrary server/debug text.
    const codes = {
      INVALID_REQUEST: "درخواست معتبر نیست. منابع دانش انتخاب‌شده را بررسی کنید.",
      SERVICE_BUSY: "سامانه در حال حاضر مشغول است. کمی بعد دوباره تلاش کنید.",
      DEPENDENCY_TIMEOUT: "زمان پاسخ‌گویی به پایان رسید. لطفاً دوباره تلاش کنید.",
      DEPENDENCY_UNAVAILABLE: "سرویس پاسخ‌گویی موقتاً در دسترس نیست.",
      DEPENDENCY_INVALID_RESPONSE: "سرویس پاسخ‌گویی پاسخ معتبری برنگرداند. لطفاً دوباره تلاش کنید.",
      // A server-side prompt budget problem; the user's question length is rarely the cause.
      MODEL_CONTEXT_LIMIT: "سامانه نتوانست به این پرسش پاسخ دهد. لطفاً کمی بعد دوباره تلاش کنید."
    };
    const details = {
      "Session not found": "گفتگو در دسترس نیست. فهرست گفتگوها را تازه‌سازی کنید.",
      "Query not found": "پیام موردنظر در دسترس نیست.",
      "No pending satisfaction request": "درخواست بازخورد فعالی وجود ندارد."
    };
    const statuses = {
      401: "لطفاً دوباره وارد حساب خود شوید.",
      403: "اجازه انجام این درخواست را ندارید.",
      404: "مورد درخواست‌شده در دسترس نیست.",
      422: "اطلاعات درخواست معتبر نیست. ورودی‌ها را بررسی کنید.",
      429: "درخواست‌های زیادی ارسال شده است. کمی بعد تلاش کنید.",
      502: "سرویس پاسخ‌گویی پاسخ معتبری برنگرداند. لطفاً دوباره تلاش کنید.",
      503: "سرویس پاسخ‌گویی موقتاً در دسترس نیست.",
      504: "زمان پاسخ‌گویی به پایان رسید. لطفاً دوباره تلاش کنید."
    };
    const description = typeof data?.detail === "string" ? data.detail : data?.errorDesc;
    return this.publicError(
      (Object.hasOwn(codes, data?.errorCode) && codes[data.errorCode]) ||
      (Object.hasOwn(details, description) && details[description]) ||
      statuses[status] || this.fallbackError
    );
  },

  async health() {
    const res = await this.request("/api/health");
    return await this.readJSON(res);
  },

  async initialize(directory) {
    const res = await this.request("/api/initialize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory_path: directory })
    });
    return await this.readJSON(res);
  },

  // async getDocuments() {
  //   const res = await this.request("/api/documents");
  //   return await this.readJSON(res);
  // },

// api.js
    async getDocuments() {
        const res = await this.request("/api/documents");
        return await this.readJSON(res);
    },

  async query(question, documents = [], sessionId,
              top_k = 10 //in nist
              , alpha = 0.5, uploadedText = null) {
    const body = {
      query: question,
      documents: documents,
      top_k: top_k,
      alpha: alpha,
      session_id: sessionId,
      uploaded_text: uploadedText     // new field
    };

    const res = await this.request("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    return await this.readJSON(res);
  },

  async streamQuery(body, { signal, onDelta }) {
    const response = await this.request("/api/query/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
    if (!response.ok) await this.readJSON(response);
    if (!response.body || response.headers.get("Content-Type")?.split(";")[0].trim() !== "text/event-stream") {
      throw this.publicError(this.fallbackError);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let pending = "";
    let event = "";
    let data = [];
    try {
      while (true) {
        const chunk = await reader.read();
        pending += decoder.decode(chunk.value, { stream: !chunk.done });
        while (pending) {
          const end = pending.search(/[\r\n]/);
          if (end === -1 || (!chunk.done && pending[end] === "\r" && end === pending.length - 1)) break;
          const line = pending.slice(0, end);
          pending = pending.slice(end + (pending.slice(end, end + 2) === "\r\n" ? 2 : 1));
          if (line === "") {
            if (data.length && ["delta", "done", "error"].includes(event)) {
              const payload = JSON.parse(data.join("\n"));
              if (event === "error") throw this.responseError(payload);
              if (event === "done" && payload?.status === "success" &&
                  typeof payload.answer === "string" && typeof payload.query_id === "string") {
                return payload;
              }
              if (event !== "delta" || typeof payload?.text !== "string") {
                throw this.publicError(this.fallbackError);
              }
              onDelta(payload.text);
            }
            event = "";
            data = [];
          } else if (!line.startsWith(":")) {
            const colon = line.indexOf(":");
            const field = colon === -1 ? line : line.slice(0, colon);
            const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
            if (field === "event") event = value;
            if (field === "data") data.push(value);
          }
        }
        if (chunk.done) throw this.publicError(this.fallbackError);
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  },

  async ocrExtract(file) {
    const form = new FormData();
    form.append("file", file);

    const res = await this.request("/api/ocr/extract", {
      method: "POST",
      body: form
    });

    return await this.readJSON(res);
  },

  async login(username, password) {
    const res = await this.request("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    return await this.readJSON(res);
  },

  async getSessions() {
    const res = await this.request("/api/sessions");
    return await this.readJSON(res);
  },

  async createSession(title = "New Chat") {
    const res = await this.request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    });
    return await this.readJSON(res);
  },

  async addMessage(sessionId, role, content) {
    const res = await this.request(`/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content })
    });
    return await this.readJSON(res);
  },

  async deleteSession(sessionId) {
    const res = await this.request(`/api/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" }
    });
    return await this.readJSON(res);
  },

  async pinSession(sessionId) {
    const res = await this.request(`/api/sessions/${sessionId}/pin`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" }
    });
    return await this.readJSON(res);
  },

  // ── Feedback: like/dislike ──
async submitFeedback(queryId, isHelpful) {
    const res = await this.request(`/api/queries/${queryId}/feedback`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_helpful: isHelpful })
    });
    return this.readJSON(res);
},

async submitComment(queryId, comment) {
    const res = await this.request(`/api/queries/${queryId}/comment`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment })
    });
    return this.readJSON(res);
},

  async submitSatisfaction(sessionId, satisfied) {
    const res = await this.request(`/api/sessions/${sessionId}/satisfaction`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ satisfied })
    });
    return this.readJSON(res);
  },

};
