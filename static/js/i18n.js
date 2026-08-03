const I18N = {
  _lang: localStorage.getItem('lang') || 'en',
  _dict: {
    en: {
      brand_name: 'Negah Bank AI',
      brand_sub: 'RAG Platform',
      nav_chat: 'Chat',
      nav_knowledge: 'Knowledge',
      nav_analytics: 'Analytics',
      new_chat: 'New Chat',
      filter_today: '📅 Today',
      filter_yesterday: '🕘 Yesterday',
      filter_last7: '📆 Last 7 days',
      filter_older: '🗄️ Older',
      topbar_title: 'Main Chat Interface',
      system_status: 'System Status',
      welcome_title: 'Ask the Bank Knowledge AI',
      welcome_subtitle: 'Search internal documents, policies and regulatory guidance.',
      lock_text: 'Please select at least one document or upload a file to start asking questions.',
      input_placeholder: 'Type your question...',
      doc_filters_title: 'Document Filters',
      search_placeholder: 'Search by name or number...',
      categories_title: 'Categories',
      active_sources_title: 'Active Sources',
      feedback_copy: 'Copy response',
      feedback_helpful: 'Helpful',
      feedback_not_helpful: 'Not helpful',
      feedback_comment: 'Add comment',
      feedback_comment_placeholder: 'Write your feedback...',
      feedback_comment_submit: 'Submit',
      session_pin: 'Pin',
      session_unpin: 'Unpin',
      session_download: 'Download',
      session_delete: 'Delete',
      session_delete_confirm: 'Are you sure you want to delete this chat? This action cannot be undone.',
      sources_related_questions: "Most Related Questions",
      feedback_submit_ticket: "Submit a Ticket",
    },
    fa: {
      brand_name: 'نگا بانک هوش مصنوعی',
      brand_sub: 'پلتفرم RAG',
      nav_chat: 'چت',
      nav_knowledge: 'دانش',
      nav_analytics: 'تحلیل',
      new_chat: 'چت جدید',
      filter_today: '📅 امروز',
      filter_yesterday: '🕘 دیروز',
      filter_last7: '📆 ۷ روز گذشته',
      filter_older: '🗄️ قدیمی‌تر',
      topbar_title: 'رابط چت اصلی',
      system_status: 'وضعیت سیستم',
      welcome_title: 'از بانک دانش هوش مصنوعی بپرسید',
      welcome_subtitle: 'اسناد داخلی، خط‌مشی‌ها و راهنماهای قانونی را جستجو کنید.',
      lock_text: 'برای شروع پرسش، حداقل یک سند انتخاب کنید یا فایلی بارگذاری نمایید',
      input_placeholder: 'سوال خود را وارد کنید...',
      doc_filters_title: 'فیلترهای سند',
      search_placeholder: 'جستجو بر اساس نام یا شماره...',
      categories_title: 'دسته‌بندی‌ها',
      active_sources_title: 'منابع فعال',
      feedback_copy: 'کپی پاسخ',
      feedback_helpful: 'مفید',
      feedback_not_helpful: 'غیرمفید',
      feedback_comment: 'افزودن نظر',
      feedback_comment_placeholder: 'نظر خود را بنویسید...',
      feedback_comment_submit: 'ثبت',
      session_pin: 'پین',
      session_unpin: 'برداشتن پین',
      session_download: 'دانلود',
      session_delete: 'حذف',
      session_delete_confirm: 'آیا از حذف این چت اطمینان دارید؟ این عملیات قابل بازگشت نیست.',
      sources_related_questions: "نزدیک ترین سوالات",
      feedback_submit_ticket: "ثبت تیکت",
    }
  },

  get lang() { return this._lang; },

  t(key) {
    return this._dict[this._lang]?.[key] || this._dict['en'][key] || key;
  },

  setLanguage(lang) {
    if (lang !== 'en' && lang !== 'fa') return;
    this._lang = lang;
    localStorage.setItem('lang', lang);
    this.applyLanguage();
    window.dispatchEvent(new CustomEvent('languagechange', { detail: lang }));
  },

  applyLanguage() {
    // Update elements with data-i18n attribute (text content)
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      el.textContent = this.t(key);
    });
    // Update placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = this.t(key);
    });
  },

  init() {
    this.applyLanguage();
  }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => I18N.init());