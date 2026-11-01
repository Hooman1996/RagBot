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
      // Only known public errors are shown. Never echo arbitrary server/debug text.
      const codes = {
        INVALID_REQUEST: "درخواست معتبر نیست. منابع دانش انتخاب‌شده را بررسی کنید.",
        SERVICE_BUSY: "سامانه در حال حاضر مشغول است. کمی بعد دوباره تلاش کنید.",
        DEPENDENCY_TIMEOUT: "زمان پاسخ‌گویی به پایان رسید. لطفاً دوباره تلاش کنید.",
        DEPENDENCY_UNAVAILABLE: "سرویس پاسخ‌گویی موقتاً در دسترس نیست.",
        MODEL_CONTEXT_LIMIT: "گفتگو برای پردازش طولانی است. پرسش کوتاه‌تری ارسال کنید."
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
        503: "سرویس پاسخ‌گویی موقتاً در دسترس نیست.",
        504: "زمان پاسخ‌گویی به پایان رسید. لطفاً دوباره تلاش کنید."
      };
      const description = typeof data?.detail === "string" ? data.detail : data?.errorDesc;
      throw this.publicError(codes[data?.errorCode] || details[description] || statuses[response.status] || this.fallbackError);
    }
    return data;
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
