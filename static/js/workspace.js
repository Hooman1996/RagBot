(() => {
    const shell = document.querySelector('.workspace-shell');
    if (!shell) return;
    const header = shell.querySelector('.workspace-topbar');
    const content = shell.querySelector('[data-workspace-content]');
    const scrim = shell.querySelector('.workspace-scrim');
    const themeButton = header.querySelector('[data-workspace-theme]');
    const themeIcon = themeButton.querySelector('use');
    const iconUrl = themeIcon.getAttribute('href').split('#')[0];
    const preference = window.matchMedia('(prefers-color-scheme: dark)');

    function setTheme(theme) {
        document.documentElement.dataset.theme = theme;
        document.body.classList.toggle('light-mode', theme === 'light');
        themeButton.setAttribute('aria-pressed', String(theme === 'dark'));
        themeIcon.setAttribute('href', `${iconUrl}#${theme === 'dark' ? 'sun' : 'moon'}`);
        window.dispatchEvent(new Event('workspace-themechange'));
    }
    function restoreTheme() {
        setTheme(localStorage.getItem('theme') || (preference.matches ? 'dark' : 'light'));
    }
    themeButton.addEventListener('click', () => {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('theme', next);
        setTheme(next);
    });
    preference.addEventListener('change', restoreTheme);
    restoreTheme();

    const drawers = [...shell.querySelectorAll('[data-workspace-toggle]')].map(trigger => {
        const name = trigger.dataset.workspaceToggle;
        const panel = shell.querySelector(`[data-workspace-panel="${name}"]`);
        return {
            name, trigger, panel,
            close: panel.querySelector('[data-workspace-close]'),
            narrow: window.matchMedia(name === 'navigation' ? '(max-width: 760px)' : '(max-width: 1020px)'),
        };
    });
    let active = null;

    function renderDrawers() {
        shell.dataset.openDrawer = active?.name || '';
        content.inert = Boolean(active);
        scrim.hidden = !active;
        for (const drawer of drawers) {
            drawer.trigger.setAttribute('aria-expanded', String(drawer === active));
            drawer.panel.inert = Boolean(active && active !== drawer) || (drawer.narrow.matches && active !== drawer);
        }
    }
    function closeDrawer() {
        if (!active) return;
        const {trigger, panel} = active;
        active = null;
        renderDrawers();
        if (trigger.getClientRects().length) trigger.focus({preventScroll: true});
        else if (panel.contains(document.activeElement) && !document.activeElement.getClientRects().length) {
            panel.querySelector('a, button:not([data-workspace-close])')?.focus({preventScroll: true});
        }
    }
    for (const drawer of drawers) {
        drawer.trigger.addEventListener('click', () => {
            if (drawer === active) {
                closeDrawer();
            } else {
                active = drawer;
                renderDrawers();
                drawer.close.focus({preventScroll: true});
            }
        });
        drawer.close.addEventListener('click', closeDrawer);
        drawer.narrow.addEventListener('change', () => {
            if (active === drawer && !drawer.narrow.matches) closeDrawer();
            else renderDrawers();
        });
    }
    scrim.addEventListener('click', closeDrawer);
    shell.addEventListener('workspace-document-selected', () => {
        if (active?.name === 'documents') closeDrawer();
    });
    document.addEventListener('keydown', event => {
        if (!active || document.querySelector('dialog[open]')) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeDrawer();
        } else if (event.key === 'Tab') {
            const controls = [...shell.querySelectorAll('button, a[href], input, select, [tabindex]')]
                .filter(el => (active.panel.contains(el) || header.contains(el)) &&
                    !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
            const next = event.shiftKey ? controls.at(-1) : controls[0];
            const edge = event.shiftKey ? controls[0] : controls.at(-1);
            if (document.activeElement === edge || !controls.includes(document.activeElement)) {
                event.preventDefault();
                next?.focus();
            }
        }
    });
    renderDrawers();
})();
