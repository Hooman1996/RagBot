/* Same-origin browser API transport. The session cookie remains HttpOnly. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const csrfCookie = 'ragbot_web_csrf';
  function csrfToken() {
    const entry = document.cookie.split('; ').find(part => part.startsWith(csrfCookie + '='));
    return entry ? decodeURIComponent(entry.slice(csrfCookie.length + 1)) : '';
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const browserApi = url.origin === window.location.origin &&
      (url.pathname.startsWith('/api/') || url.pathname.startsWith('/knowledge-base/api/')) &&
      !url.pathname.startsWith('/api/mobile/') &&
      !url.pathname.startsWith('/api/internal/evaluation/');
    if (browserApi && !['GET', 'HEAD', 'OPTIONS'].includes(method) && url.pathname !== '/api/login') {
      init = {...init, headers: new Headers(init.headers || (input instanceof Request ? input.headers : undefined))};
      init.headers.set('X-CSRF-Token', csrfToken());
    }
    const response = await nativeFetch(input, init);
    if (browserApi && response.status === 401 && url.pathname !== '/api/login') {
      window.location.assign('/');
    }
    return response;
  };
  window.webLogout = async () => {
    const response = await fetch('/api/auth/logout', {method: 'POST'});
    if (response.ok) window.location.assign('/');
  };
})();
