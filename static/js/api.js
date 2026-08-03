const API = {
  async health() {
    const res = await fetch("/api/health");
    return await res.json();
  },

  async initialize(directory) {
    const res = await fetch("/api/initialize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory_path: directory })
    });
    return await res.json();
  },

  // async getDocuments() {
  //   const res = await fetch("/api/documents");
  //   return await res.json();
  // },

// api.js
    async getDocuments() {
        const res = await fetch("/api/documents");
        return await res.json();
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

    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    return await res.json();
  },

  async ocrExtract(file) {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch("/api/ocr/extract", {
      method: "POST",
      body: form
    });

    return await res.json();
  },

  async login(username, password) {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    return await res.json();
  },

  async getSessions() {
    const res = await fetch("/api/sessions");
    return await res.json();
  },

  async createSession(title = "New Chat") {
    const res = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    });
    return await res.json();
  },

  async addMessage(sessionId, role, content) {
    const res = await fetch(`/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content })
    });
    return await res.json();
  },

  async deleteSession(sessionId) {
    const res = await fetch(`/api/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" }
    });
    return await res.json();
  },

  async pinSession(sessionId) {
    const res = await fetch(`/api/sessions/${sessionId}/pin`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" }
    });
    return await res.json();
  },

  // ── Feedback: like/dislike ──
async submitFeedback(queryId, isHelpful) {
    const res = await fetch(`/api/queries/${queryId}/feedback`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_helpful: isHelpful })
    });
    if (!res.ok) throw new Error("Feedback request failed");
    return res.json();
},

async submitComment(queryId, comment) {
    const res = await fetch(`/api/queries/${queryId}/comment`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment })
    });
    if (!res.ok) throw new Error("Comment request failed");
    return res.json();
},

  submitSatisfaction: async (sessionId, satisfied) => {
    const res = await fetch(`/api/sessions/${sessionId}/satisfaction`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ satisfied })
    });
    if (!res.ok) throw new Error("Satisfaction submission failed");
    return res.json();
  },

};
