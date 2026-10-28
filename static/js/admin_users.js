/* Admin-only account creation; the shared web_auth transport adds CSRF. */
(() => {
  const fields = ['username', 'email', 'full_name', 'role', 'password', 'confirm_password'];
  const messages = {
    en: {
      users_add: 'Add user', users_username: 'Username', users_email: 'Email', users_full_name: 'Full name',
      users_role: 'Role', users_password: 'Password', users_confirm_password: 'Confirm password',
      users_hint: 'Create an account with access defined by its role.',
      users_password_hint: 'Use a nonempty password of at most 72 UTF-8 bytes, without NUL.',
      users_loading: 'Creating user…', users_success: 'User created', users_invalid: 'Check the highlighted fields.',
      users_username_error: 'Use 1–100 characters with no whitespace or control characters.',
      users_email_error: 'Enter a trimmed email address (name@domain.tld), at most 255 characters.',
      users_full_name_error: 'Enter a full name of 1–255 characters, without control characters.',
      users_role_error: 'Choose a supported role.', users_password_error: 'Use 1–72 UTF-8 bytes, without NUL.',
      users_confirm_password_error: 'Passwords must match exactly.', users_fields_error: 'Supply all six form fields.',
      users_duplicate_username: 'Username already exists.', users_duplicate_email: 'Email already exists.',
      users_duplicate_form: 'Account conflicts with an existing record.',
      users_forbidden: 'Access denied. Sign in with an admin account.', users_session: 'Session expired. Sign in again.',
      users_unavailable: 'User creation is unavailable. Check with your administrator before retrying.',
      users_network: 'Could not confirm creation. Check with your administrator before retrying.'
    },
    fa: {
      users_add: 'افزودن کاربر', users_username: 'نام کاربری', users_email: 'ایمیل', users_full_name: 'نام و نام خانوادگی',
      users_role: 'نقش', users_password: 'رمز عبور', users_confirm_password: 'تکرار رمز عبور',
      users_hint: 'حساب جدید با دسترسی‌های تعیین‌شده بر اساس نقش ایجاد کنید.',
      users_password_hint: 'رمز عبور نباید خالی باشد و حداکثر ۷۲ بایت UTF-8، بدون نویسه NUL باشد.',
      users_loading: 'در حال ایجاد کاربر…', users_success: 'کاربر ایجاد شد', users_invalid: 'فیلدهای مشخص‌شده را بررسی کنید.',
      users_username_error: '۱ تا ۱۰۰ نویسه بدون فاصله یا نویسه کنترلی وارد کنید.',
      users_email_error: 'ایمیل معتبر (name@domain.tld) با حداکثر ۲۵۵ نویسه و بدون فاصله وارد کنید.',
      users_full_name_error: 'نام کامل با ۱ تا ۲۵۵ نویسه و بدون نویسه کنترلی وارد کنید.',
      users_role_error: 'یکی از نقش‌های مجاز را انتخاب کنید.', users_password_error: 'رمز عبور باید ۱ تا ۷۲ بایت UTF-8 و بدون NUL باشد.',
      users_confirm_password_error: 'رمزهای عبور باید دقیقاً یکسان باشند.', users_fields_error: 'هر شش فیلد فرم را تکمیل کنید.',
      users_duplicate_username: 'نام کاربری از قبل وجود دارد.', users_duplicate_email: 'ایمیل از قبل وجود دارد.',
      users_duplicate_form: 'حساب با یک رکورد موجود تداخل دارد.',
      users_forbidden: 'دسترسی مجاز نیست. با حساب مدیر وارد شوید.', users_session: 'نشست منقضی شده است. دوباره وارد شوید.',
      users_unavailable: 'ایجاد کاربر در دسترس نیست. پیش از تلاش مجدد با مدیر سامانه بررسی کنید.',
      users_network: 'ایجاد حساب تأیید نشد. پیش از تلاش مجدد با مدیر سامانه بررسی کنید.'
    }
  };
  const length = value => Array.from(value).length;
  const control = /[\x00-\x1f\x7f]/;
  const whitespace = /[\s\u0085\u001c-\u001f]/;
  const trimmed = value => value.replace(/^[\s\u0085\u001c-\u001f]+|[\s\u0085\u001c-\u001f]+$/g, '');
  function validText(value, max, spaces = false) {
    return !!value && trimmed(value) === value && length(value) <= max && !control.test(value) && (spaces || !whitespace.test(value));
  }
  function validate(data, roles) {
    const errors = {};
    if (!validText(data.username, 100)) errors.username = 'username';
    if (!validText(data.email, 255) || !/^[^@\s\u0085]+@[^@\s\u0085]+\.[^@\s\u0085]+$/.test(data.email)) errors.email = 'email';
    if (!validText(trimmed(data.full_name), 255, true)) errors.full_name = 'full_name';
    if (!roles.includes(data.role)) errors.role = 'role';
    if (!data.password || data.password.includes('\x00') || new TextEncoder().encode(data.password).length > 72) errors.password = 'password';
    if (data.password !== data.confirm_password) errors.confirm_password = 'confirm_password';
    return errors;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {validate, messages};
  if (typeof document === 'undefined') return;
  Object.keys(messages).forEach(lang => Object.assign(I18N._dict[lang], messages[lang]));
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('usersForm');
    const submit = document.getElementById('usersSubmit');
    const error = document.getElementById('usersError');
    const status = document.getElementById('usersStatus');
    const controls = Object.fromEntries(fields.map(field => [field, document.getElementById('user-' + field)]));
    const roles = Array.from(controls.role.options, option => option.value);
    let busy = false, errors = {}, notice = '', created = null;
    const t = key => I18N.t(key);
    function render() {
      document.documentElement.lang = I18N.lang;
      document.documentElement.dir = I18N.lang === 'fa' ? 'rtl' : 'ltr';
      document.body.classList.toggle('rtl', I18N.lang === 'fa');
      document.querySelectorAll('[data-lang]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.lang === I18N.lang)));
      fields.forEach(field => {
        const hint = document.getElementById('error-' + field);
        const code = errors[field];
        hint.hidden = !code;
        hint.textContent = code ? t(code === 'duplicate' ? 'users_duplicate_' + field : 'users_' + code + '_error') : '';
        controls[field].setAttribute('aria-invalid', String(!!code));
      });
      error.hidden = !notice;
      error.textContent = notice ? t(notice) : '';
      status.hidden = !busy && !created;
      status.textContent = busy ? t('users_loading') : created ? `${t('users_success')}: ${created.username} · ${created.role} · #${created.id}` : '';
      submit.disabled = busy;
      submit.textContent = t(busy ? 'users_loading' : 'users_add');
      form.setAttribute('aria-busy', String(busy));
    }
    const theme = document.getElementById('usersTheme');
    document.body.classList.toggle('light-mode', localStorage.getItem('theme') === 'light');
    theme.addEventListener('click', () => {
      const light = document.body.classList.toggle('light-mode');
      localStorage.setItem('theme', light ? 'light' : 'dark');
    });
    document.querySelectorAll('[data-lang]').forEach(button => button.addEventListener('click', () => I18N.setLanguage(button.dataset.lang)));
    window.addEventListener('languagechange', render);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      const data = Object.fromEntries(fields.map(field => [field, controls[field].value]));
      errors = validate(data, roles);
      notice = Object.keys(errors).length ? 'users_invalid' : '';
      created = null;
      if (notice) {
        render();
        controls[Object.keys(errors)[0]].focus();
        return;
      }
      busy = true;
      render();
      try {
        const response = await fetch('/api/admin/users', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
        // Server error text is never rendered; only documented field/code pairs are accepted.
        const result = await response.json();
        if (response.status === 201) {
          created = result.user;
          controls.password.value = '';
          controls.confirm_password.value = '';
        } else if (response.status === 422 || response.status === 409) {
          const codes = ['username', 'email', 'full_name', 'password', 'role', 'confirm_password', 'duplicate'];
          for (const field of fields) if (codes.includes(result.errors?.[field])) errors[field] = result.errors[field];
          notice = response.status === 409 && !Object.keys(errors).length ? 'users_duplicate_form' : 'users_invalid';
        } else {
          notice = response.status === 401 ? 'users_session' : response.status === 403 ? 'users_forbidden' : 'users_unavailable';
        }
      } catch {
        notice = 'users_network';
      } finally {
        busy = false;
        render();
        if (created) status.focus();
        else if (Object.keys(errors).length) controls[Object.keys(errors)[0]].focus();
        else error.focus();
      }
    });
    render();
    document.querySelector?.('[aria-current="page"]')?.scrollIntoView({block: 'nearest', inline: 'nearest'});
  });
})();
