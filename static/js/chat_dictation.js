class ChatDictation {
  // Keep provider traffic out of the RagBot CSRF and session-expiration transport.
  static #fetch = window.fetch.bind(window);
  static #formats = {
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/mp4': 'mp4',
  };
  static #healthInterval = 30_000;
  static #recordingLimit = 45_000;
  static #recordingFinalizeTimeout = 3_000;
  static #microphoneErrors = new Map([
    ['NotAllowedError', 'dictation_denied'],
    ['SecurityError', 'dictation_denied'],
    ['NotFoundError', 'dictation_microphone_missing'],
    ['NotReadableError', 'dictation_microphone_unavailable'],
    ['AbortError', 'dictation_microphone_unavailable'],
  ]);

  constructor(chat, mic) {
    this.chat = chat;
    this.mic = mic;
    this.stopButton = document.getElementById('dictationStop');
    this.cancelButton = document.getElementById('dictationCancel');
    this.status = document.getElementById('dictationStatus');
    this.origin = mic.dataset.asrOrigin;
    this.message = '';
    this.ready = false;
    this.operation = null;
    this.healthCheck = null;
    this.lastHealthCheck = -Infinity;

    this.render();
    window.addEventListener('languagechange', () => this.render());
    if (!this.origin || !window.isSecureContext || !navigator.mediaDevices?.getUserMedia ||
        !window.MediaRecorder?.isTypeSupported) return;

    this.mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus',
      'audio/mp4', 'audio/webm', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type));
    if (!this.mimeType) return;

    this.mic.addEventListener('click', () => this.start());
    this.stopButton.addEventListener('click', () => this.stop());
    this.cancelButton.addEventListener('click', () => this.finish('dictation_cancelled', true));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        this.checkHealth();
      } else if (this.operation?.phase === 'permission' || this.operation?.stream) {
        this.cancel();
      }
    });
    window.addEventListener('pagehide', () => {
      this.cancel();
      this.healthCheck?.abort();
      this.healthCheck = null;
      this.ready = false;
      this.render();
      clearInterval(this.healthTimer);
    });
    window.addEventListener('pageshow', event => {
      if (event.persisted) this.startHealthPolling();
    });
    this.startHealthPolling();
  }

  startHealthPolling() {
    this.lastHealthCheck = -Infinity;
    this.checkHealth();
    this.healthTimer = setInterval(() => this.checkHealth(), ChatDictation.#healthInterval);
  }

  async checkHealth() {
    const now = performance.now();
    if (document.visibilityState !== 'visible' || this.healthCheck ||
        now - this.lastHealthCheck < ChatDictation.#healthInterval) return;
    this.lastHealthCheck = now;
    const controller = new AbortController();
    this.healthCheck = controller;
    let ready = false;
    try {
      const {data} = await this.fetchJson('/api/health', {}, 3_000, controller);
      ready = data?.status === 'ok' && data?.model_loaded === true;
    } catch {
      // Readiness is advisory. Typing and uploads remain available.
    } finally {
      if (this.healthCheck === controller) {
        this.healthCheck = null;
        this.ready = ready;
        this.render();
      }
    }
  }

  async fetchJson(path, options, timeout, controller) {
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await ChatDictation.#fetch(this.origin + path, {
        ...options,
        mode: 'cors',
        credentials: 'omit',
        redirect: 'error',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
        signal: controller.signal,
      });
      const data = response.ok ? await response.json() : null;
      if (controller.signal.aborted) throw controller.signal.reason;
      return {status: response.status, data};
    } finally {
      clearTimeout(timer);
    }
  }

  render() {
    const phase = this.operation?.phase;
    this.mic.disabled = !this.ready || this.chat.isLocked || this.chat.isSending || Boolean(phase);
    this.stopButton.hidden = phase !== 'recording';
    this.cancelButton.hidden = !phase;
    const label = I18N.t('dictation_start');
    this.mic.setAttribute('aria-label', label);
    this.mic.title = label;
    const status = this.message ? I18N.t(this.message) : '';
    if (this.status.textContent !== status) this.status.textContent = status;
  }

  async start() {
    if (this.mic.disabled || document.visibilityState !== 'visible') return;
    const operation = {phase: 'permission', chunks: []};
    this.operation = operation;
    this.message = 'dictation_permission';
    const restoreFocus = document.activeElement === this.mic;
    this.render();
    if (restoreFocus) this.cancelButton.focus();

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
    } catch (error) {
      if (this.operation === operation) {
        const message = ChatDictation.#microphoneErrors.get(error?.name) || 'dictation_capture_error';
        this.finish(message, true);
      }
      return;
    }
    if (this.operation !== operation) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    operation.stream = stream;
    try {
      const recorder = new MediaRecorder(stream, {mimeType: this.mimeType});
      operation.recorder = recorder;
      recorder.addEventListener('dataavailable', ({data}) => {
        if (this.operation === operation && data.size) operation.chunks.push(data);
      });
      recorder.addEventListener('stop', () => this.transcribe(operation));
      recorder.addEventListener('error', () => {
        if (this.operation === operation) this.finish('dictation_capture_error', true);
      });
      recorder.start();
      operation.phase = 'recording';
      operation.startedAt = performance.now();
      operation.recordingTimer = setTimeout(() => this.stop(), ChatDictation.#recordingLimit);
      this.message = 'dictation_recording';
      this.render();
    } catch {
      this.finish('dictation_capture_error', true);
    }
  }

  stop() {
    const operation = this.operation;
    if (operation?.phase !== 'recording') return;
    if (performance.now() - operation.startedAt >= 60_000 || operation.recorder.state === 'inactive') {
      this.finish('dictation_capture_error', true);
      return;
    }
    operation.phase = 'transcribing';
    this.message = 'dictation_transcribing';
    const moveFocus = document.activeElement === this.stopButton;
    clearTimeout(operation.recordingTimer);
    try {
      // Keep the audio track live until the recorder has flushed its final data.
      operation.recorder.stop();
    } catch {
      this.finish('dictation_capture_error', true);
      return;
    }
    operation.finalizationTimer = setTimeout(() => {
      if (this.operation === operation) this.finish('dictation_capture_error', true);
    }, ChatDictation.#recordingFinalizeTimeout);
    this.render();
    if (moveFocus) this.cancelButton.focus();
  }

  releaseMicrophone(operation) {
    clearTimeout(operation.recordingTimer);
    clearTimeout(operation.finalizationTimer);
    operation.stream?.getTracks().forEach(track => track.stop());
    operation.stream = null;
  }

  async transcribe(operation) {
    if (this.operation !== operation) return;
    if (operation.phase !== 'transcribing') {
      this.finish('dictation_capture_error', true);
      return;
    }
    this.releaseMicrophone(operation);
    const mimeType = operation.chunks[0]?.type || operation.recorder.mimeType;
    const extension = ChatDictation.#formats[mimeType.split(';')[0].trim().toLowerCase()];
    if (!operation.chunks.length) {
      this.finish('dictation_empty_recording', true);
      return;
    }
    if (!extension) {
      this.finish('dictation_capture_error', true);
      return;
    }

    const form = new FormData();
    form.append('file', new Blob(operation.chunks, {type: mimeType}), `dictation.${extension}`);
    operation.chunks.length = 0;
    const controller = new AbortController();
    operation.controller = controller;
    try {
      const {status, data} = await this.fetchJson('/api/transcribe', {method: 'POST', body: form}, 30_000, controller);
      if (this.operation !== operation) return;
      const transcript = typeof data?.text === 'string' ? data.text.trim() : '';
      if (status === 429) {
        this.finish('dictation_busy', true);
      } else if (status < 200 || status >= 300 || typeof data?.text !== 'string') {
        this.finish('dictation_error', true);
      } else if (!transcript) {
        this.finish('dictation_empty', true);
      } else {
        const draft = this.chat.textarea.value;
        this.chat.textarea.value = draft + (draft && !/\s$/.test(draft) ? ' ' : '') + transcript;
        this.finish('dictation_added', true);
      }
    } catch {
      if (this.operation === operation) {
        this.finish(controller.signal.aborted ? 'dictation_timeout' : 'dictation_error', true);
      }
    }
  }

  cancel() {
    this.finish('');
  }

  finish(message, restoreFocus = false) {
    const operation = this.operation;
    const moveFocus = restoreFocus && [this.stopButton, this.cancelButton].includes(document.activeElement);
    this.operation = null;
    this.message = message;
    if (operation) {
      this.releaseMicrophone(operation);
      operation.chunks.length = 0;
      operation.controller?.abort();
    }
    this.render();
    if (moveFocus) (this.mic.disabled ? this.chat.textarea : this.mic).focus();
  }
}
