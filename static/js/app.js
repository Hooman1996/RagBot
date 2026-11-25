/* Workspace controls. Language changes update labels in place so chat state is untouched. */
function initChatPreferences() {
  const root = document.documentElement;
  const languageButtons = document.querySelectorAll('.lang-option');
  const logout = document.querySelector('.web-logout');
  logout.dataset.i18nLabel = 'logout';
  logout.dataset.i18nTitle = 'logout';

  function renderLanguage() {
    root.lang = I18N.lang;
    for (const button of languageButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.lang === I18N.lang));
    }
  }

  for (const button of languageButtons) {
    button.addEventListener('click', () => I18N.setLanguage(button.dataset.lang));
  }
  window.addEventListener('languagechange', renderLanguage);
  renderLanguage();

  const theme = document.getElementById('themeToggleBtn');
  const icon = theme.querySelector('use');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  function renderTheme(value) {
    root.dataset.theme = value;
    theme.setAttribute('aria-pressed', String(value === 'dark'));
    icon.setAttribute('href', `${document.body.dataset.iconsUrl}#${value === 'dark' ? 'sun' : 'moon'}`);
  }
  function restoreTheme() {
    renderTheme(localStorage.getItem('theme') || (systemTheme.matches ? 'dark' : 'light'));
  }
  systemTheme.addEventListener('change', restoreTheme);
  theme.addEventListener('click', () => {
    const value = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', value);
    renderTheme(value);
  });
  restoreTheme();
}

function initChatPanels() {
  const shell = document.querySelector('.app-shell');
  const header = document.querySelector('.topbar');
  const chat = document.querySelector('.chat-main');
  const scrim = document.getElementById('drawer-scrim');
  const panels = {
    history: {
      element: document.getElementById('chat-history'),
      trigger: document.getElementById('history-toggle'),
      narrow: window.matchMedia('(max-width: 760px)'),
    },
    documents: {
      element: document.getElementById('chat-documents'),
      trigger: document.getElementById('documents-toggle'),
      narrow: window.matchMedia('(max-width: 1020px)'),
    },
  };
  let drawer = null;
  let documentsOpen = true;

  function render() {
    const { history, documents } = panels;
    shell.classList.toggle('history-drawer', drawer === 'history');
    shell.classList.toggle('documents-drawer', drawer === 'documents');
    shell.classList.toggle('documents-closed', !documents.narrow.matches && !documentsOpen);
    history.trigger.setAttribute('aria-expanded', String(drawer === 'history'));
    documents.trigger.setAttribute('aria-expanded',
      String(documents.narrow.matches ? drawer === 'documents' : documentsOpen));
    chat.inert = Boolean(drawer);
    history.element.inert = drawer === 'documents';
    documents.element.inert = drawer === 'history';
    scrim.hidden = !drawer;
  }

  function closeDrawer() {
    if (!drawer) return;
    const { trigger } = panels[drawer];
    drawer = null;
    Sessions.closeMenu();
    render();
    if (trigger.getClientRects().length) trigger.focus({preventScroll: true});
  }

  for (const [name, panel] of Object.entries(panels)) {
    const close = panel.element.querySelector('[data-close-panel]');
    panel.trigger.addEventListener('click', () => {
      if (panel.narrow.matches) {
        if (drawer === name) {
          closeDrawer();
        } else {
          Sessions.closeMenu();
          drawer = name;
          render();
          close.focus({preventScroll: true});
        }
      } else if (name === 'documents') {
        documentsOpen = !documentsOpen;
        render();
      }
    });
    close.addEventListener('click', () => {
      if (drawer === name) closeDrawer();
      else if (name === 'documents') {
        documentsOpen = false;
        render();
        panel.trigger.focus({preventScroll: true});
      }
    });
    panel.narrow.addEventListener('change', () => {
      if (drawer === name && !panel.narrow.matches) closeDrawer();
      else render();
    });
  }

  scrim.addEventListener('click', closeDrawer);
  window.addEventListener('batch-documents-requested', () => {
    const { element, narrow } = panels.documents;
    Sessions.closeMenu();
    if (narrow.matches) drawer = 'documents';
    else documentsOpen = true;
    render();
    element.querySelector('input[type="search"]').focus();
  });
  window.addEventListener('conversationselected', () => {
    if (drawer === 'history') closeDrawer();
  });
  document.addEventListener('keydown', event => {
    if (document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') {
      if (Sessions.closeMenu(true)) event.preventDefault();
      else if (drawer) {
        event.preventDefault();
        closeDrawer();
      }
    }

    // Keep the header in the tab order so language and theme are available with a drawer open.
    if (!drawer || event.key !== 'Tab') return;
    const panel = panels[drawer].element;
    const controls = [...document.querySelectorAll('button, a[href], input, select, summary, [tabindex]')]
      .filter(element => (panel.contains(element) || header.contains(element)) &&
        !element.disabled && element.tabIndex >= 0 && element.getClientRects().length);
    const first = controls[0];
    const last = controls.at(-1);
    if (!controls.includes(document.activeElement) || document.activeElement === (event.shiftKey ? first : last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  });

  // iOS can resize only the visual viewport when the keyboard opens.
  const viewport = window.visualViewport;
  if (viewport) {
    const fitViewport = () => {
      if (viewport.scale === 1) {
        shell.style.setProperty('--chat-viewport-height', `${viewport.height}px`);
      } else {
        shell.style.removeProperty('--chat-viewport-height');
      }
    };
    viewport.addEventListener('resize', fitViewport);
    fitViewport();
  }
  render();
}

async function initChatHealth() {
  const chip = document.getElementById('systemHealth');
  const label = chip.querySelector('.status-label');
  const dot = document.getElementById('healthDot');
  let healthy = false;
  try {
    healthy = (await API.health()).status === 'healthy';
  } catch (_) {
    // Keep the unavailable status when the health endpoint cannot be reached.
  }
  const key = healthy ? 'chat_health_ok' : 'chat_health_error';
  label.dataset.i18n = key;
  label.textContent = I18N.t(key);
  chip.dataset.i18nTitle = key;
  chip.title = label.textContent;
  dot.classList.add(healthy ? 'dot-green' : 'dot-red');
}

function initChatBatch() {
  const dialog = document.getElementById('batch-dialog');
  if (!dialog) return;
  const button = document.getElementById('batch-upload-btn');
  const form = document.getElementById('batch-form');
  const input = document.getElementById('batch-file-input');
  const sources = document.getElementById('batch-document-list');
  const empty = document.getElementById('batch-no-documents');
  const choose = document.getElementById('batch-choose-documents');
  const run = document.getElementById('batch-run');
  const download = document.getElementById('batch-download');
  const progress = document.getElementById('batch-progress');
  const status = document.getElementById('batch-status');
  let busy = false;
  let jobDocuments = [];
  let message;
  let result;

  function render() {
    const documents = busy || result ? jobDocuments : Chat.selectedDocs;
    sources.replaceChildren(...documents.map(name => {
      const item = document.createElement('li');
      item.dir = 'auto';
      item.textContent = name;
      return item;
    }));
    sources.hidden = !documents.length;
    empty.hidden = Boolean(documents.length);
    choose.disabled = busy;
    input.disabled = busy;
    run.disabled = busy || !input.files.length || !Chat.selectedDocs.length;
    download.hidden = !result;
    form.setAttribute('aria-busy', String(busy));
    progress.hidden = !busy;
    status.hidden = !message;
    status.textContent = message ? I18N.t(message.key, message.values) : '';
    status.classList.toggle('error', message?.key === 'chat_batch_error');
  }

  function show(key, values) {
    message = {key, values};
    render();
  }

  function downloadResult() {
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Answered_${result.fileName}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  button.addEventListener('click', () => {
    render();
    dialog.showModal();
  });
  document.getElementById('batch-close').addEventListener('click', () => dialog.close());
  choose.addEventListener('click', () => {
    dialog.close();
    window.dispatchEvent(new Event('batch-documents-requested'));
  });
  input.addEventListener('change', () => {
    result = null;
    message = null;
    render();
  });
  download.addEventListener('click', downloadResult);
  window.addEventListener('languagechange', () => {
    if (dialog.open) render();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const file = input.files[0];
    if (!file || busy || !Chat.selectedDocs.length) return;

    busy = true;
    jobDocuments = Chat.selectedDocs.slice();
    result = null;
    progress.removeAttribute('value');
    show('chat_batch_processing');
    const data = new FormData();
    data.append('file', file);
    data.append('session_id', Sessions.currentSessionId || '0');
    data.append('selected_docs', JSON.stringify(jobDocuments));

    try {
      let response = await API.request('/api/mass-answer', {method: 'POST', body: data});
      if (response.status === 202) {
        const job = await API.readJSON(response);
        const options = {headers: {'X-Job-Access': job.job_access}};
        while (true) {
          await new Promise(resolve => setTimeout(resolve, 2000));
          const jobStatus = await API.readJSON(await API.request(job.status_url, options));
          if (jobStatus.total_rows) {
            progress.max = jobStatus.total_rows;
            progress.value = jobStatus.completed_rows;
            show('chat_batch_progress', {done: jobStatus.completed_rows, total: jobStatus.total_rows});
          }
          if (['failed', 'cancelled'].includes(jobStatus.status)) throw new Error();
          if (jobStatus.status === 'completed') {
            response = await API.request(jobStatus.result_url, options);
            break;
          }
        }
      }
      if (!response.ok) await API.readJSON(response);
      result = {blob: await response.blob(), fileName: file.name};
      input.value = '';
      show('chat_batch_done');
      downloadResult();
    } catch (_) {
      show('chat_batch_error');
    } finally {
      busy = false;
      render();
      if (dialog.open && document.activeElement === dialog) (result ? download : run).focus();
    }
  });
}

initChatPreferences();
document.addEventListener('DOMContentLoaded', () => {
  Chat.init();
  initChatPanels();
  Sessions.init();
  CategoryFilter.init();
  initChatHealth();
  initChatBatch();
});
